"""Synthetic workflow contracts, with no credentials or live remote calls."""
import io
import os
from contextlib import closing, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from notion_client import NotionClient
from parser import parse_meeting_notes


class PortfolioWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.dict(os.environ, {"MEETING_DB_PATH": self.temp.name + "/notes.db"}):
            import app
            import database
        self.app_module = app
        self.database = database
        db_path = patch.object(database, "DB_PATH", self.temp.name + "/notes.db")
        db_path.start()
        self.addCleanup(db_path.stop)
        database.init_db()
        # Never read a developer's real local config or send real HTTP requests.
        self.config = {"notion_token": "synthetic", "notion_database_id": "demo-db",
                       "clickup_token": "synthetic", "clickup_list_id": "demo-list",
                       "jira_domain": "example.invalid", "jira_email": "demo@example.invalid",
                       "jira_api_token": "synthetic", "jira_parent_key": "DEMO-1",
                       "anthropic_api_key": "synthetic"}
        for patcher in (patch.object(app, "load_config", return_value=self.config),
                        patch("requests.get", side_effect=AssertionError("Unexpected network")),
                        patch("requests.post", side_effect=AssertionError("Unexpected network"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = app.app.test_client()

    def import_notes(self):
        page = {"id": "synthetic-page", "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "Invented review"}]},
            "Date": {"type": "date", "date": {"start": "2026-11-09"}}},
            "url": "https://example.invalid/synthetic-notes"}
        # Supported Notion heading and paragraph shapes, including bold text.
        def block(kind, *rich_text):
            return {"type": kind, kind: {"rich_text": list(rich_text)}}
        def text(value, bold=False):
            return {"plain_text": value, "annotations": {"bold": bold}}
        blocks = [
            block("heading_3", text("1. DECISIONS LOG")),
            block("paragraph", text("- "), text("[DEMO-1]", True), text(" Use invented data | Decided by: Demo team")),
            block("heading_3", text("2. JIRA TICKETS")),
            block("paragraph", text("- "), text("Title:", True), text(" Review form")),
            block("paragraph", text("- "), text("Description:", True), text(" Human review required")),
            block("heading_3", text("3. CLICKUP TICKETS")),
            block("paragraph", text("- "), text("Title:", True), text(" Prepare checklist")),
        ]
        client = NotionClient("synthetic")
        client.get_all_database_pages = Mock(return_value=[page])
        client.get_page_blocks = Mock(return_value=blocks)
        with patch.object(self.app_module, "NotionClient", return_value=client):
            first = self.client.post("/api/sync-notion")
            again = self.client.post("/api/sync-notion")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json["imported"], 1)
        self.assertEqual(again.json["skipped"], 1)

    def test_synthetic_example_has_all_five_sections(self):
        example = Path(__file__).resolve().parents[1] / "examples/synthetic_meeting_notes.md"
        parsed = parse_meeting_notes(example.read_text())
        self.assertEqual({key: len(value) for key, value in parsed.items()}, {
            "decisions": 1, "jira_tickets": 1, "clickup_tickets": 1,
            "customer_topics": 1, "internal_topics": 1})

    def test_notion_import_stays_local_until_review_action(self):
        self.import_notes()
        with closing(self.database.get_db()) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT status FROM clickup_tickets").fetchone()[0], "pending")
        self.assertEqual(self.client.get("/meetings/1").status_code, 200)
        task = Mock(return_value={"id": "DEMO-TASK", "url": "https://example.invalid/task"})
        with patch.object(self.app_module.ClickUpClient, "create_task", task):
            result = self.client.post("/api/clickup/create-task", json={"ticket_id": 1})
            again = self.client.post("/api/clickup/create-task", json={"ticket_id": 1})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(again.status_code, 409)
        task.assert_called_once()

    def test_cancelled_drafts_do_not_create_remote_items(self):
        self.import_notes()
        with closing(self.database.get_db()) as db, db:
            db.execute("UPDATE clickup_tickets SET status='cancelled'")
            db.execute("UPDATE jira_tickets SET status='cancelled'")
        for endpoint in ("/api/clickup/create-task", "/api/jira/create-subtask"):
            self.assertEqual(self.client.post(endpoint, json={"ticket_id": 1}).status_code, 409)

    def test_chat_sends_to_claude_without_payload_file_or_content_logs(self):
        transcript = "Synthetic private-marker text for a mocked request."
        with closing(self.database.get_db()) as db, db:
            db.execute("INSERT INTO transcriptions (title, meeting_date, content) VALUES (?,?,?)",
                       ("Invented review", "2026-11-09", transcript))
        remote = Mock(status_code=200)
        remote.json.return_value = {"content": [{"type": "text", "text": "Review the invented source."}]}
        output = io.StringIO()
        with patch("builtins.open", side_effect=AssertionError("Must not write debug payload")), \
             patch.object(self.app_module.http_requests, "post", return_value=remote) as post, \
             patch.dict(os.environ, {"ANTHROPIC_MODEL": "synthetic-model"}), redirect_stdout(output):
            response = self.client.post("/api/chat", json={
                "message": "Invented review 2026-11-09: summarize", "include_context": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(post.call_args.args[0], "https://api.anthropic.com/v1/messages")
        self.assertIn(transcript, post.call_args.kwargs["json"]["system"])
        self.assertEqual(post.call_args.kwargs["json"]["model"], "synthetic-model")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(response.json["meeting_ref"], "Invented review | 2026-11-09")

    def test_jira_create_is_explicit_and_prevents_resend(self):
        self.import_notes()
        remote = Mock(status_code=201)
        remote.json.return_value = {"key": "DEMO-2"}
        with patch.object(self.app_module.http_requests, "post", return_value=remote) as post:
            response = self.client.post("/api/jira/create-subtask", json={"ticket_id": 1})
            repeated = self.client.post("/api/jira/create-subtask", json={"ticket_id": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json["issue_key"], "DEMO-2")
        self.assertEqual(repeated.status_code, 409)
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
