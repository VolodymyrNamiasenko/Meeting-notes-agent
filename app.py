import os
import json
import re
import uuid
import secrets
import requests as http_requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from database import get_db, init_db, DB_PATH
from parser import parse_meeting_notes
from notion_client import NotionClient
from clickup_client import ClickUpClient
from jira_client import JiraClient

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", MAX_CONTENT_LENGTH=20 * 1024 * 1024)

# ----- Config -----
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ==================== PAGES ====================

@app.route("/")
def dashboard():
    db = get_db()
    stats = {
        "meetings": db.execute("SELECT COUNT(*) c FROM meetings").fetchone()["c"],
        "decisions": db.execute("SELECT COUNT(*) c FROM decisions").fetchone()["c"],
        "jira_pending": db.execute("SELECT COUNT(*) c FROM jira_tickets WHERE (status IS NULL OR status='pending') AND resolved=0").fetchone()["c"],
        "jira_resolved": db.execute("SELECT COUNT(*) c FROM jira_tickets WHERE resolved=1 OR status='created'").fetchone()["c"],
        "jira_created": db.execute("SELECT COUNT(*) c FROM jira_tickets WHERE status='created'").fetchone()["c"],
        "jira_cancelled": db.execute("SELECT COUNT(*) c FROM jira_tickets WHERE status='cancelled'").fetchone()["c"],
        "clickup_pending": db.execute("SELECT COUNT(*) c FROM clickup_tickets WHERE status='pending'").fetchone()["c"],
        "clickup_created": db.execute("SELECT COUNT(*) c FROM clickup_tickets WHERE status='created'").fetchone()["c"],
        "clickup_cancelled": db.execute("SELECT COUNT(*) c FROM clickup_tickets WHERE status='cancelled'").fetchone()["c"],
        "customer_topics_open": db.execute("SELECT COUNT(*) c FROM customer_topics WHERE resolved=0").fetchone()["c"],
        "internal_topics_open": db.execute("SELECT COUNT(*) c FROM internal_topics WHERE resolved=0").fetchone()["c"],
    }
    recent_meetings = db.execute(
        "SELECT * FROM meetings ORDER BY meeting_date DESC, imported_at DESC LIMIT 10"
    ).fetchall()
    db.close()
    return render_template("dashboard.html", stats=stats, recent_meetings=recent_meetings)


@app.route("/meetings")
def meetings_list():
    db = get_db()
    meetings = db.execute("SELECT * FROM meetings ORDER BY meeting_date DESC, imported_at DESC").fetchall()
    db.close()
    return render_template("meetings.html", meetings=meetings)


@app.route("/meetings/<int:meeting_id>")
def meeting_detail(meeting_id):
    db = get_db()
    meeting = db.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    if not meeting:
        db.close()
        return "Meeting not found", 404

    data = {
        "meeting": meeting,
        "decisions": db.execute("SELECT * FROM decisions WHERE meeting_id=?", (meeting_id,)).fetchall(),
        "jira_tickets": db.execute("SELECT * FROM jira_tickets WHERE meeting_id=?", (meeting_id,)).fetchall(),
        "clickup_tickets": db.execute("SELECT * FROM clickup_tickets WHERE meeting_id=?", (meeting_id,)).fetchall(),
        "customer_topics": db.execute("SELECT * FROM customer_topics WHERE meeting_id=?", (meeting_id,)).fetchall(),
        "internal_topics": db.execute("SELECT * FROM internal_topics WHERE meeting_id=?", (meeting_id,)).fetchall(),
    }

    # Build a summary of all items for highlighting
    item_summary = {
        "decisions": len(data["decisions"]),
        "jira_pending": sum(1 for t in data["jira_tickets"] if (t["status"] or "pending") == "pending"),
        "jira_created": sum(1 for t in data["jira_tickets"] if t["status"] == "created"),
        "jira_cancelled": sum(1 for t in data["jira_tickets"] if t["status"] == "cancelled"),
        "clickup_pending": sum(1 for t in data["clickup_tickets"] if t["status"] == "pending"),
        "clickup_created": sum(1 for t in data["clickup_tickets"] if t["status"] == "created"),
        "clickup_cancelled": sum(1 for t in data["clickup_tickets"] if t["status"] == "cancelled"),
        "customer_topics_open": sum(1 for t in data["customer_topics"] if not t["resolved"]),
        "customer_topics_resolved": sum(1 for t in data["customer_topics"] if t["resolved"]),
        "internal_topics_open": sum(1 for t in data["internal_topics"] if not t["resolved"]),
        "internal_topics_resolved": sum(1 for t in data["internal_topics"] if t["resolved"]),
    }
    data["item_summary"] = item_summary

    config = load_config()
    data["config"] = config
    db.close()
    return render_template("meeting_detail.html", **data)


@app.route("/decisions")
def decisions_list():
    db = get_db()
    rows = db.execute("""
        SELECT d.*, m.title as meeting_title, m.meeting_date, m.notion_url
        FROM decisions d
        JOIN meetings m ON d.meeting_id = m.id
        ORDER BY m.meeting_date DESC, d.decision_code
    """).fetchall()
    db.close()
    return render_template("decisions.html", decisions=rows)


@app.route("/jira")
def jira_list():
    db = get_db()
    rows = db.execute("""
        SELECT j.*, m.title as meeting_title, m.meeting_date, m.notion_url
        FROM jira_tickets j
        JOIN meetings m ON j.meeting_id = m.id
        ORDER BY j.resolved ASC, m.meeting_date DESC
    """).fetchall()
    db.close()
    config = load_config()
    return render_template("jira.html", tickets=rows, config=config)


@app.route("/clickup")
def clickup_list():
    db = get_db()
    rows = db.execute("""
        SELECT c.*, m.title as meeting_title, m.meeting_date, m.notion_url
        FROM clickup_tickets c
        JOIN meetings m ON c.meeting_id = m.id
        ORDER BY c.status ASC, m.meeting_date DESC
    """).fetchall()
    db.close()
    config = load_config()
    return render_template("clickup.html", tickets=rows, config=config)


@app.route("/topics")
def topics_list():
    db = get_db()
    customer = db.execute("""
        SELECT t.*, m.title as meeting_title, m.meeting_date, m.notion_url
        FROM customer_topics t
        JOIN meetings m ON t.meeting_id = m.id
        ORDER BY t.resolved ASC, m.meeting_date DESC
    """).fetchall()
    internal = db.execute("""
        SELECT t.*, m.title as meeting_title, m.meeting_date, m.notion_url
        FROM internal_topics t
        JOIN meetings m ON t.meeting_id = m.id
        ORDER BY t.resolved ASC, m.meeting_date DESC
    """).fetchall()
    db.close()
    return render_template("topics.html", customer_topics=customer, internal_topics=internal)


@app.route("/statistics")
def statistics_page():
    db = get_db()
    meetings = db.execute("""
        SELECT m.*,
            (SELECT COUNT(*) FROM decisions WHERE meeting_id=m.id) as decision_count,
            (SELECT COUNT(*) FROM jira_tickets WHERE meeting_id=m.id) as jira_count,
            (SELECT COUNT(*) FROM clickup_tickets WHERE meeting_id=m.id) as clickup_count,
            (SELECT COUNT(*) FROM customer_topics WHERE meeting_id=m.id) as customer_topic_count,
            (SELECT COUNT(*) FROM internal_topics WHERE meeting_id=m.id) as internal_topic_count
        FROM meetings m
        ORDER BY m.meeting_date DESC
    """).fetchall()

    # Derive meeting duration (minutes) from matching transcription content.
    # Transcripts contain HH:MM:SS timestamps per speaker turn; the max timestamp
    # is taken as the meeting length.
    transcriptions = db.execute(
        "SELECT id, title, meeting_date, content FROM transcriptions WHERE content IS NOT NULL"
    ).fetchall()

    ts_rows = []
    for t in transcriptions:
        content = t["content"] or ""
        matches = re.findall(r"(\d{1,2}):(\d{2}):(\d{2})", content)
        if not matches:
            continue
        max_secs = max(int(h) * 3600 + int(mm) * 60 + int(s) for h, mm, s in matches)
        ts_rows.append({
            "id": t["id"],
            "title": (t["title"] or "").lower(),
            "date": (t["meeting_date"] or "")[:10],
            "minutes": max_secs / 60.0,
            "used": False,
        })

    def _words(s):
        return set(re.findall(r"\w{4,}", (s or "").lower()))

    # Pass 1: compute best-candidate overlap per meeting, then greedily assign
    # each transcription to the meeting with the highest title-word overlap on
    # that date. This prevents the same transcription being counted multiple
    # times when several meetings share a date.
    meetings_by_date = {}
    for idx, m in enumerate(meetings):
        d = (m["meeting_date"] or "")[:10]
        meetings_by_date.setdefault(d, []).append(idx)

    duration_by_idx = {i: 0.0 for i in range(len(meetings))}
    for date_key, idx_list in meetings_by_date.items():
        if not date_key:
            continue
        candidates = [t for t in ts_rows if t["date"] == date_key]
        if not candidates:
            continue
        # Build (meeting_idx, transcription, overlap) tuples, sort desc by overlap
        pairs = []
        for i in idx_list:
            mw = _words(meetings[i]["title"])
            for t in candidates:
                ov = len(mw & _words(t["title"]))
                pairs.append((ov, i, t))
        pairs.sort(key=lambda x: -x[0])

        assigned_meetings = set()
        for ov, i, t in pairs:
            if t["used"] or i in assigned_meetings:
                continue
            # Require overlap > 0, OR allow zero-overlap only if exactly one
            # meeting and one transcription share the date.
            if ov > 0 or (len(idx_list) == 1 and len(candidates) == 1):
                duration_by_idx[i] = t["minutes"]
                t["used"] = True
                assigned_meetings.add(i)

    meetings_out = []
    for i, m in enumerate(meetings):
        d = dict(m)
        d["duration_minutes"] = round(duration_by_idx[i], 1)
        meetings_out.append(d)

    db.close()
    return render_template("statistics.html", meetings=meetings_out)


@app.route("/settings")
def settings_page():
    config = load_config()
    return render_template("settings.html", config=config)


# ==================== API ENDPOINTS ====================

@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json
    config = load_config()
    config.update(data)
    save_config(config)
    return jsonify({"ok": True})


@app.route("/api/sync-notion", methods=["POST"])
def sync_notion():
    """Fetch all pages from the Notion database, parse and store them."""
    config = load_config()
    notion_token = config.get("notion_token")
    notion_db_id = config.get("notion_database_id")

    if not notion_token or not notion_db_id:
        return jsonify({"error": "Notion token and database ID required. Configure in Settings."}), 400

    try:
        client = NotionClient(notion_token)
        pages = client.get_all_database_pages(notion_db_id)

        db = get_db()
        imported = 0
        skipped = 0

        for page in pages:
            page_id = page["id"]

            # Check if already imported
            existing = db.execute("SELECT id FROM meetings WHERE notion_page_id=?", (page_id,)).fetchone()
            if existing:
                skipped += 1
                continue

            # Fetch page content
            blocks = client.get_page_blocks(page_id)
            markdown = client.blocks_to_markdown(blocks)
            title = client.get_page_title(page)
            meeting_date = client.get_page_date(page)
            notion_url = client.get_page_url(page)

            # Parse the structured notes
            parsed = parse_meeting_notes(markdown)

            # Insert meeting
            cursor = db.execute(
                """INSERT INTO meetings (notion_page_id, title, meeting_date, notion_url, raw_content)
                   VALUES (?, ?, ?, ?, ?)""",
                (page_id, title, meeting_date, notion_url, markdown)
            )
            meeting_id = cursor.lastrowid

            # Insert parsed items
            for d in parsed["decisions"]:
                db.execute(
                    "INSERT INTO decisions (meeting_id, decision_code, summary, decided_by) VALUES (?,?,?,?)",
                    (meeting_id, d["code"], d["summary"], d["decided_by"])
                )

            for t in parsed["jira_tickets"]:
                db.execute(
                    "INSERT INTO jira_tickets (meeting_id, title, description) VALUES (?,?,?)",
                    (meeting_id, t["title"], t["description"])
                )

            for t in parsed["clickup_tickets"]:
                db.execute(
                    "INSERT INTO clickup_tickets (meeting_id, title, description) VALUES (?,?,?)",
                    (meeting_id, t["title"], t["description"])
                )

            for t in parsed["customer_topics"]:
                db.execute(
                    "INSERT INTO customer_topics (meeting_id, topic, context) VALUES (?,?,?)",
                    (meeting_id, t["topic"], t["context"])
                )

            for t in parsed["internal_topics"]:
                db.execute(
                    "INSERT INTO internal_topics (meeting_id, topic, context) VALUES (?,?,?)",
                    (meeting_id, t["topic"], t["context"])
                )

            imported += 1

        db.commit()
        db.close()
        return jsonify({"ok": True, "imported": imported, "skipped": skipped, "total_pages": len(pages)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resync-meeting/<int:meeting_id>", methods=["POST"])
def resync_meeting(meeting_id):
    """Re-fetch and re-parse a single meeting from Notion."""
    config = load_config()
    notion_token = config.get("notion_token")
    if not notion_token:
        return jsonify({"error": "Notion token required"}), 400

    db = get_db()
    meeting = db.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    try:
        client = NotionClient(notion_token)
        page_id = meeting["notion_page_id"]
        page = client.get_page(page_id)
        blocks = client.get_page_blocks(page_id)
        markdown = client.blocks_to_markdown(blocks)
        title = client.get_page_title(page)
        meeting_date = client.get_page_date(page)

        parsed = parse_meeting_notes(markdown)

        # Clear old data
        for table in ["decisions", "jira_tickets", "clickup_tickets", "customer_topics", "internal_topics"]:
            db.execute(f"DELETE FROM {table} WHERE meeting_id=?", (meeting_id,))

        # Update meeting
        db.execute(
            "UPDATE meetings SET title=?, meeting_date=?, raw_content=? WHERE id=?",
            (title, meeting_date, markdown, meeting_id)
        )

        # Re-insert parsed items
        for d in parsed["decisions"]:
            db.execute(
                "INSERT INTO decisions (meeting_id, decision_code, summary, decided_by) VALUES (?,?,?,?)",
                (meeting_id, d["code"], d["summary"], d["decided_by"])
            )
        for t in parsed["jira_tickets"]:
            db.execute(
                "INSERT INTO jira_tickets (meeting_id, title, description) VALUES (?,?,?)",
                (meeting_id, t["title"], t["description"])
            )
        for t in parsed["clickup_tickets"]:
            db.execute(
                "INSERT INTO clickup_tickets (meeting_id, title, description) VALUES (?,?,?)",
                (meeting_id, t["title"], t["description"])
            )
        for t in parsed["customer_topics"]:
            db.execute(
                "INSERT INTO customer_topics (meeting_id, topic, context) VALUES (?,?,?)",
                (meeting_id, t["topic"], t["context"])
            )
        for t in parsed["internal_topics"]:
            db.execute(
                "INSERT INTO internal_topics (meeting_id, topic, context) VALUES (?,?,?)",
                (meeting_id, t["topic"], t["context"])
            )

        db.commit()
        db.close()
        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clickup/create-task", methods=["POST"])
def create_clickup_task():
    """Push a ticket to ClickUp."""
    config = load_config()
    clickup_token = config.get("clickup_token")
    clickup_list_id = config.get("clickup_list_id")

    if not clickup_token or not clickup_list_id:
        return jsonify({"error": "ClickUp token and list ID required. Configure in Settings."}), 400

    data = request.json
    ticket_id = data.get("ticket_id")

    db = get_db()
    ticket = db.execute("""
        SELECT c.*, m.title as meeting_title, m.meeting_date
        FROM clickup_tickets c
        JOIN meetings m ON c.meeting_id = m.id
        WHERE c.id=?
    """, (ticket_id,)).fetchone()
    if not ticket:
        db.close()
        return jsonify({"error": "Ticket not found"}), 404

    if (ticket["status"] or "pending") != "pending":
        db.close()
        return jsonify({"error": "Only pending drafts can be sent. Review the existing item or cancellation."}), 409

    try:
        client = ClickUpClient(clickup_token)
        desc = ticket["description"] or ""
        meeting_ref = f"Meeting: {ticket['meeting_title']}"
        if ticket["meeting_date"]:
            meeting_ref += f" ({ticket['meeting_date']})"
        full_desc = f"{meeting_ref}\n\n{desc}" if desc else meeting_ref
        result = client.create_task(clickup_list_id, ticket["title"], full_desc)

        db.execute(
            "UPDATE clickup_tickets SET status='created', clickup_task_id=?, created_in_clickup_at=? WHERE id=?",
            (result.get("id"), datetime.now().isoformat(), ticket_id)
        )
        db.commit()
        db.close()
        return jsonify({"ok": True, "task_id": result.get("id"), "url": result.get("url")})

    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/topics/<string:topic_type>/<int:topic_id>/toggle", methods=["POST"])
def toggle_topic(topic_type, topic_id):
    """Toggle resolved status of a topic."""
    table = "customer_topics" if topic_type == "customer" else "internal_topics"
    db = get_db()
    db.execute(f"UPDATE {table} SET resolved = NOT resolved WHERE id=?", (topic_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/clickup/cancel", methods=["POST"])
def cancel_clickup_ticket():
    """Cancel a pending ClickUp ticket (mark as cancelled instead of creating)."""
    data = request.json
    ticket_id = data.get("ticket_id")

    db = get_db()
    ticket = db.execute("SELECT * FROM clickup_tickets WHERE id=?", (ticket_id,)).fetchone()
    if not ticket:
        db.close()
        return jsonify({"error": "Ticket not found"}), 404

    db.execute(
        "UPDATE clickup_tickets SET status='cancelled' WHERE id=?",
        (ticket_id,)
    )
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/jira/<int:ticket_id>/toggle-resolved", methods=["POST"])
def toggle_jira_resolved(ticket_id):
    """Toggle resolved status of a JIRA ticket."""
    db = get_db()
    db.execute("UPDATE jira_tickets SET resolved = NOT resolved WHERE id=?", (ticket_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/jira/create-subtask", methods=["POST"])
def create_jira_subtask():
    """Create a sub-task in Jira under the configured parent task."""
    config = load_config()
    jira_domain = config.get("jira_domain", "").strip()
    jira_email = config.get("jira_email", "").strip()
    jira_api_token = config.get("jira_api_token", "").strip()
    jira_parent_key = config.get("jira_parent_key", "").strip()
    jira_assignee_email = config.get("jira_assignee_email", "").strip()

    if not jira_domain or not jira_email or not jira_api_token or not jira_parent_key:
        return jsonify({"error": "Jira settings incomplete. Configure domain, email, API token, and parent task key in Settings."}), 400

    data = request.json
    ticket_id = data.get("ticket_id")

    db = get_db()
    ticket = db.execute("""
        SELECT j.*, m.title as meeting_title, m.meeting_date
        FROM jira_tickets j
        JOIN meetings m ON j.meeting_id = m.id
        WHERE j.id=?
    """, (ticket_id,)).fetchone()
    if not ticket:
        db.close()
        return jsonify({"error": "Ticket not found"}), 404

    if (ticket["status"] or "pending") != "pending":
        db.close()
        return jsonify({"error": "Only pending drafts can be sent. Review the existing item or cancellation."}), 409

    try:
        # Build the subtask payload
        base_url = f"https://{jira_domain}/rest/api/3"
        auth = (jira_email, jira_api_token)

        desc_text = ticket["description"] or ""
        meeting_ref = f"Meeting: {ticket['meeting_title']}"
        if ticket["meeting_date"]:
            meeting_ref += f" ({ticket['meeting_date']})"
        full_desc = f"{meeting_ref}\n\n{desc_text}" if desc_text else meeting_ref

        payload = {
            "fields": {
                "parent": {"key": jira_parent_key},
                "project": {"key": jira_parent_key.split("-")[0]},
                "summary": ticket["title"],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": full_desc}]
                        }
                    ]
                },
                "issuetype": {"name": "Sub-task"}
            }
        }

        # Auto-assign if assignee email is configured
        if jira_assignee_email:
            # Look up the Jira account ID by email
            search_resp = http_requests.get(
                f"{base_url}/user/search?query={jira_assignee_email}",
                auth=auth,
                headers={"Accept": "application/json"},
                timeout=30,
            )
            if search_resp.status_code == 200:
                users = search_resp.json()
                if users:
                    payload["fields"]["assignee"] = {"accountId": users[0]["accountId"]}

        resp = http_requests.post(
            f"{base_url}/issue",
            auth=auth,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )

        if resp.status_code not in (200, 201):
            error_detail = resp.text[:500]
            db.close()
            return jsonify({"error": f"Jira API error ({resp.status_code}): {error_detail}"}), 500

        result = resp.json()
        issue_key = result.get("key", "")
        issue_url = f"https://{jira_domain}/browse/{issue_key}"

        db.execute(
            "UPDATE jira_tickets SET status='created', jira_issue_key=?, created_in_jira_at=? WHERE id=?",
            (issue_key, datetime.now().isoformat(), ticket_id)
        )
        db.commit()
        db.close()
        return jsonify({"ok": True, "issue_key": issue_key, "url": issue_url})

    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/jira/cancel", methods=["POST"])
def cancel_jira_ticket():
    """Cancel a pending Jira ticket."""
    data = request.json
    ticket_id = data.get("ticket_id")

    db = get_db()
    ticket = db.execute("SELECT * FROM jira_tickets WHERE id=?", (ticket_id,)).fetchone()
    if not ticket:
        db.close()
        return jsonify({"error": "Ticket not found"}), 404

    db.execute("UPDATE jira_tickets SET status='cancelled' WHERE id=?", (ticket_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/delete-meeting/<int:meeting_id>", methods=["DELETE"])
def delete_meeting(meeting_id):
    db = get_db()
    db.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


# ==================== TRANSCRIPTIONS ====================

@app.route("/transcriptions")
def transcriptions_list():
    db = get_db()
    transcriptions = db.execute(
        "SELECT * FROM transcriptions ORDER BY meeting_date DESC, imported_at DESC"
    ).fetchall()
    db.close()
    return render_template("transcriptions.html", transcriptions=transcriptions)


@app.route("/transcriptions/<int:transcription_id>")
def transcription_detail(transcription_id):
    db = get_db()
    transcription = db.execute("SELECT * FROM transcriptions WHERE id=?", (transcription_id,)).fetchone()
    db.close()
    if not transcription:
        return "Transcription not found", 404
    return render_template("transcription_detail.html", transcription=transcription)


@app.route("/api/sync-transcriptions", methods=["POST"])
def sync_transcriptions():
    """Fetch all pages from the Transcriptions Notion database."""
    config = load_config()
    notion_token = config.get("notion_token")
    trans_db_id = config.get("transcriptions_database_id")

    if not notion_token:
        return jsonify({"error": "Notion API token required. Configure in Settings."}), 400
    if not trans_db_id:
        return jsonify({"error": "Transcriptions Database ID required. Configure in Settings."}), 400

    try:
        client = NotionClient(notion_token)
        pages = client.get_all_database_pages(trans_db_id)

        db = get_db()
        imported = 0
        skipped = 0

        for page in pages:
            page_id = page["id"]

            existing = db.execute("SELECT id FROM transcriptions WHERE notion_page_id=?", (page_id,)).fetchone()
            if existing:
                skipped += 1
                continue

            blocks = client.get_page_blocks(page_id)
            markdown = client.blocks_to_markdown(blocks)
            title = client.get_page_title(page)
            meeting_date = client.get_page_date(page)
            notion_url = client.get_page_url(page)

            db.execute(
                """INSERT INTO transcriptions (notion_page_id, title, meeting_date, notion_url, content)
                   VALUES (?, ?, ?, ?, ?)""",
                (page_id, title, meeting_date, notion_url, markdown)
            )
            imported += 1

        db.commit()
        db.close()
        return jsonify({"ok": True, "imported": imported, "skipped": skipped, "total_pages": len(pages)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== CHAT AGENT ====================

@app.route("/chat")
def chat_page():
    db = get_db()
    transcription_count = db.execute("SELECT COUNT(*) c FROM transcriptions").fetchone()["c"]
    sessions = db.execute(
        "SELECT id, name, meeting_ref, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC"
    ).fetchall()
    db.close()
    current_session_id = session.get("chat_session_id")
    return render_template("chat.html",
        transcription_count=transcription_count,
        sessions=sessions,
        current_session_id=current_session_id,
    )


def _find_meeting_in_message(user_message, db):
    """
    Try to extract a meeting reference from the user message.
    Matches by title AND date (YYYY-MM-DD portion only).
    Handles stored dates like '2026-04-10T13:20:00.000+04:00'.
    """
    transcriptions = db.execute(
        "SELECT id, title, meeting_date FROM transcriptions"
    ).fetchall()

    if not transcriptions:
        return None

    msg_lower = user_message.lower().strip()

    # Extract all YYYY-MM-DD dates from user message
    msg_dates = re.findall(r'\d{4}-\d{2}-\d{2}', user_message)

    best_match_id = None
    best_score = 0

    for t in transcriptions:
        title = (t["title"] or "").strip()
        raw_date = (t["meeting_date"] or "").strip()
        if not title and not raw_date:
            continue

        title_lower = title.lower()

        # Extract just YYYY-MM-DD from stored date (handles "2026-04-10T13:20:00.000+04:00")
        stored_date_short = raw_date[:10] if len(raw_date) >= 10 else raw_date

        score = 0

        # Title match: check if stored title appears in message
        title_found = title_lower and title_lower in msg_lower
        if title_found:
            score += 2

        # Date match: compare YYYY-MM-DD only
        date_found = stored_date_short and stored_date_short in msg_dates
        if date_found:
            score += 2

        if score > best_score:
            best_score = score
            best_match_id = t["id"]


    # Require both title AND date to match (score >= 4)
    if best_score >= 4 and best_match_id:
        return db.execute(
            "SELECT id, title, meeting_date, content FROM transcriptions WHERE id=?",
            (best_match_id,)
        ).fetchone()
    return None


def _generate_session_name(user_message, meeting_ref=None, api_key=None):
    """Generate a short session name using the first message."""
    # Truncate question for name
    short_q = user_message[:60].strip()
    if len(user_message) > 60:
        short_q += "..."

    if meeting_ref:
        return f"{meeting_ref} — {short_q}"
    return short_q


@app.route("/api/chat", methods=["POST"])
def chat_api():
    """Send a message to the Claude API with meeting-aware context."""
    config = load_config()
    api_key = config.get("anthropic_api_key")
    if not api_key:
        return jsonify({"error": "Anthropic API key not configured. Go to Settings to add it."}), 400

    data = request.json
    user_message = data.get("message", "").strip()
    include_context = data.get("include_context", True)
    target_session_id = data.get("session_id")

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    db = get_db()

    # Session management
    session_id = target_session_id or session.get("chat_session_id")
    is_new_session = False

    if not session_id:
        session_id = str(uuid.uuid4())
        is_new_session = True

    # Check if session exists in DB
    existing = db.execute("SELECT id FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
    if not existing:
        is_new_session = True

    session["chat_session_id"] = session_id

    # Build conversation history
    history_rows = db.execute(
        "SELECT role, content FROM chat_history WHERE session_id=? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    messages = [{"role": r["role"], "content": r["content"]} for r in history_rows]

    # Build system prompt
    system_prompt = config.get("system_prompt", "").strip()
    if not system_prompt:
        system_prompt = "You are a helpful project assistant. Answer questions clearly and concisely."

    # Try to find a specific meeting reference in the message
    meeting_match = None
    meeting_ref_label = None
    meeting_not_found_warning = None
    context_truncated = False

    if include_context:
        meeting_match = _find_meeting_in_message(user_message, db)

        if meeting_match:
            # Specific meeting found — send that full transcription (capped)
            title = meeting_match["title"]
            date = meeting_match["meeting_date"] or "No date"
            content = meeting_match["content"] or ""
            date_short = date[:10] if len(date) >= 10 else date
            meeting_ref_label = f"{title} | {date_short}"
            # Cap at 80K chars to avoid timeout on very long transcriptions
            context_truncated = False
            if len(content) > 80000:
                context_truncated = True
                content = content[:80000] + "\n\n[... transcription truncated due to length ...]"
            context_block = f"--- {title} ({date_short}) ---\n{content}\n"
            system_prompt += f"\n\n<meeting_transcriptions>\n{context_block}\n</meeting_transcriptions>\n\nThe user is asking about a specific meeting: {title} ({date_short}). Use the full transcription above as context. Reference the meeting by title and date."
        else:
            # Check if user seems to be referencing a specific meeting that wasn't found
            has_meeting_ref = bool(re.search(r'\[.+\|.+\]', user_message) or re.search(r'\[.+\d{4}-\d{2}-\d{2}', user_message))

            if has_meeting_ref:
                # User referenced a meeting but we couldn't match it — warn them
                available = db.execute("SELECT title, meeting_date FROM transcriptions ORDER BY meeting_date DESC LIMIT 30").fetchall()
                available_list = "\n".join([f"  - {a['title']} | {(a['meeting_date'] or '')[:10]}" for a in available])
                meeting_not_found_warning = (
                    f"⚠ Could not find a matching meeting transcription for your reference.\n\n"
                    f"Available meetings:\n{available_list}\n\n"
                    f"Please check the meeting name and date match exactly."
                )

            # No specific meeting — fall back to recent transcriptions
            transcriptions = db.execute(
                "SELECT title, meeting_date, content FROM transcriptions ORDER BY meeting_date DESC LIMIT 20"
            ).fetchall()
            if transcriptions:
                context_parts = []
                total_chars = 0
                max_chars = 80000
                for t in transcriptions:
                    entry = f"--- {t['title']} ({t['meeting_date'] or 'No date'}) ---\n{t['content'] or ''}\n"
                    if total_chars + len(entry) > max_chars:
                        break
                    context_parts.append(entry)
                    total_chars += len(entry)
                if context_parts:
                    context_block = "\n".join(context_parts)
                    system_prompt += f"\n\n<meeting_transcriptions>\n{context_block}\n</meeting_transcriptions>\n\nUse the meeting transcriptions above as context when answering questions. Reference specific meetings by title and date when relevant."

    # If meeting reference was in the message but not matched, return warning immediately
    if meeting_not_found_warning:
        db.close()
        return jsonify({
            "response": meeting_not_found_warning,
            "session_id": session_id,
            "is_new_session": False,
            "session_name": None,
            "meeting_ref": None,
        })

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    try:
        resp = http_requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=300,
        )

        if resp.status_code != 200:
            error_detail = resp.json().get("error", {}).get("message", resp.text[:200])
            db.close()
            return jsonify({"error": f"API error ({resp.status_code}): {error_detail}"}), 500

        result = resp.json()
        assistant_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                assistant_text += block.get("text", "")

        # Create session if new
        session_name = None
        if is_new_session:
            session_name = _generate_session_name(user_message, meeting_ref_label)
            db.execute(
                "INSERT INTO chat_sessions (id, name, meeting_ref, created_at, updated_at) VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                (session_id, session_name, meeting_ref_label)
            )

        # Update session timestamp
        db.execute("UPDATE chat_sessions SET updated_at=datetime('now') WHERE id=?", (session_id,))

        # Save messages to history
        db.execute(
            "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, "user", user_message)
        )
        db.execute(
            "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, "assistant", assistant_text)
        )
        db.commit()
        db.close()

        return jsonify({
            "response": assistant_text,
            "session_id": session_id,
            "is_new_session": is_new_session,
            "session_name": session_name if is_new_session else None,
            "meeting_ref": meeting_ref_label,
            "context_truncated": context_truncated,
        })

    except http_requests.exceptions.Timeout:
        db.close()
        return jsonify({"error": "Request timed out. Try again."}), 504
    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/sessions", methods=["GET"])
def chat_sessions_list():
    """List all chat sessions, optionally filtered by search query."""
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        sessions = db.execute(
            "SELECT id, name, meeting_ref, created_at, updated_at FROM chat_sessions WHERE name LIKE ? ORDER BY updated_at DESC",
            (f"%{q}%",)
        ).fetchall()
    else:
        sessions = db.execute(
            "SELECT id, name, meeting_ref, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC"
        ).fetchall()
    db.close()
    return jsonify({"sessions": [dict(s) for s in sessions]})


@app.route("/api/chat/sessions/<session_id>", methods=["GET"])
def chat_session_detail(session_id):
    """Load a specific session's messages."""
    db = get_db()
    sess = db.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
    if not sess:
        db.close()
        return jsonify({"error": "Session not found"}), 404
    messages = db.execute(
        "SELECT role, content, created_at FROM chat_history WHERE session_id=? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    db.close()
    session["chat_session_id"] = session_id
    return jsonify({
        "session": dict(sess),
        "messages": [dict(m) for m in messages],
    })


@app.route("/api/chat/sessions/<session_id>", methods=["DELETE"])
def chat_session_delete(session_id):
    """Delete a session and its messages."""
    db = get_db()
    db.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))
    db.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    db.commit()
    db.close()
    if session.get("chat_session_id") == session_id:
        session.pop("chat_session_id", None)
    return jsonify({"ok": True})


@app.route("/api/chat/sessions/new", methods=["POST"])
def chat_session_new():
    """Create a new empty session and switch to it."""
    new_id = str(uuid.uuid4())
    session["chat_session_id"] = new_id
    return jsonify({"session_id": new_id})


@app.route("/api/chat/clear", methods=["POST"])
def chat_clear():
    """Clear chat history for current session."""
    session_id = session.get("chat_session_id")
    if session_id:
        db = get_db()
        db.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))
        db.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
        db.commit()
        db.close()
    session["chat_session_id"] = str(uuid.uuid4())
    return jsonify({"ok": True})


# Initialize for both the CLI and WSGI imports (e.g. gunicorn app:app).
init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", "5001")))
