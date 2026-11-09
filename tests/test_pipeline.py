import io
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import audio_transcription
import meeting_pipeline as pipeline

SOURCE = "We agreed to use a test database. Alex will prepare the review checklist. We must discuss the rollout date."
NOTES = {
    "summary": "Use a test database and prepare the review checklist.",
    "decisions": [
        {
            "text": "Use a test database",
            "owner": "",
            "quote": "We agreed to use a test database.",
        }
    ],
    "actions": [
        {
            "title": "Prepare review checklist",
            "description": "For the test rollout",
            "owner": "Alex",
            "destination": "clickup",
            "quote": "Alex will prepare the review checklist.",
        }
    ],
    "topics": [
        {
            "text": "Rollout date",
            "audience": "internal",
            "quote": "We must discuss the rollout date.",
        }
    ],
}


class PipelineTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.dict(os.environ, {"MEETING_DB_PATH": self.temp.name + "/notes.db"}):
            import app
            import database
        self.app = app
        self.db = database
        p = patch.object(database, "DB_PATH", self.temp.name + "/notes.db")
        p.start()
        self.addCleanup(p.stop)
        database.init_db()
        self.client = app.app.test_client()
        p = patch.object(
            app, "load_config", return_value={"anthropic_api_key": "synthetic"}
        )
        p.start()
        self.addCleanup(p.stop)
        self.network = patch(
            "requests.post", side_effect=AssertionError("Unexpected external call")
        )
        self.network.start()
        self.addCleanup(self.network.stop)

    def import_text(self):
        response = self.client.post(
            "/api/pipeline/import",
            json={
                "title": "Invented meeting",
                "meeting_date": "2026-11-09",
                "content": SOURCE,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json["id"]

    def count(self, table):
        with closing(self.db.get_db()) as db:
            return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_import_deduplicates_and_validates_metadata(self):
        identifier = self.import_text()
        again = self.client.post(
            "/api/pipeline/import",
            json={
                "title": "Invented meeting",
                "meeting_date": "2026-11-09",
                "content": SOURCE,
            },
        )
        self.assertTrue(again.json["duplicate"])
        self.assertEqual(again.json["id"], identifier)
        self.assertEqual(self.count("transcriptions"), 1)
        for body in [
            {},
            {"title": "x", "content": "x", "meeting_date": "2026-02-31"},
            {"title": "x", "content": True},
        ]:
            self.assertEqual(
                self.client.post("/api/pipeline/import", json=body).status_code, 400
            )

    def test_manual_draft_review_creates_only_local_pending_tasks_once(self):
        identifier = self.import_text()
        created = self.client.post(
            f"/api/pipeline/transcripts/{identifier}/draft", json={"notes": NOTES}
        )
        self.assertEqual(created.status_code, 201, created.text)
        draft = created.json
        self.assertEqual(self.count("meetings"), 0)
        self.assertEqual(self.count("clickup_tickets"), 0)
        self.assertEqual(self.client.get("/pipeline").status_code, 200)
        body = {
            "version": 1,
            "reviewer": "Demo reviewer",
            "decision": "approved",
            "note": "Compared with transcript",
        }
        applied = self.client.post(
            f"/api/pipeline/drafts/{draft['id']}/review", json=body
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(self.count("meetings"), 1)
        self.assertEqual(self.count("decisions"), 1)
        with closing(self.db.get_db()) as db:
            self.assertEqual(
                db.execute("SELECT status FROM clickup_tickets").fetchone()[0],
                "pending",
            )
        repeated = self.client.post(
            f"/api/pipeline/drafts/{draft['id']}/review", json=body
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(self.count("meetings"), 1)
        self.assertEqual(
            self.client.get(f"/meetings/{applied.json['meeting_id']}").status_code, 200
        )

    def test_unsupported_quote_owner_and_extra_fields_rejected(self):
        identifier = self.import_text()
        for change in ["quote", "owner", "extra"]:
            value = json.loads(json.dumps(NOTES))
            if change == "quote":
                value["actions"][0]["quote"] = "This was never said in the meeting."
            elif change == "owner":
                value["actions"][0]["owner"] = "Invented owner"
            else:
                value["unexpected"] = "ignore evidence"
            self.assertEqual(
                self.client.post(
                    f"/api/pipeline/transcripts/{identifier}/draft",
                    json={"notes": value},
                ).status_code,
                400,
            )
        self.assertEqual(self.count("meeting_drafts"), 0)

    def test_edit_version_conflict_and_reject_no_side_effects(self):
        identifier = self.import_text()
        record = pipeline.save_draft(identifier, NOTES, "manual")
        edited = self.client.post(
            f"/api/pipeline/drafts/{record['id']}/edit",
            json={"version": 1, "reviewer": "Demo", "notes": NOTES},
        )
        self.assertEqual(edited.status_code, 200)
        stale = self.client.post(
            f"/api/pipeline/drafts/{record['id']}/review",
            json={"version": 1, "reviewer": "Demo", "decision": "approved"},
        )
        self.assertEqual(stale.status_code, 409)
        rejected = self.client.post(
            f"/api/pipeline/drafts/{record['id']}/review",
            json={"version": 2, "reviewer": "Demo", "decision": "rejected"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(self.count("meetings"), 0)
        self.assertEqual(
            [e["action"] for e in rejected.json["events"]],
            ["generated", "edited", "rejected"],
        )

    def test_ai_generation_requires_permission_and_validates_remote_output(self):
        identifier = self.import_text()
        self.assertEqual(
            self.client.post(
                f"/api/pipeline/transcripts/{identifier}/generate", json={}
            ).status_code,
            400,
        )
        remote = Mock()
        remote.json.return_value = {
            "content": [{"type": "text", "text": json.dumps(NOTES)}],
            "stop_reason": "end_turn",
        }
        with (
            patch.dict(
                os.environ,
                {
                    "ANTHROPIC_API_KEY": "synthetic",
                    "ANTHROPIC_MODEL": "synthetic-model",
                },
            ),
            patch("requests.post", return_value=remote) as post,
        ):
            result = self.client.post(
                f"/api/pipeline/transcripts/{identifier}/generate",
                json={"allow_external": True},
            )
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json["provider"], "claude")
        self.assertEqual(post.call_args.kwargs["timeout"], 90)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "synthetic-model")
        self.assertIn(SOURCE, post.call_args.kwargs["json"]["messages"][0]["content"])
        self.assertEqual(self.count("meetings"), 0)
        for invalid in [
            "not JSON",
            json.dumps({**NOTES, "actions": [{"title": "Fake"}]}),
        ]:
            remote.json.return_value = {"content": [{"type": "text", "text": invalid}]}
            with (
                patch("requests.post", return_value=remote),
                self.assertRaises(pipeline.PipelineError),
            ):
                pipeline.generate_notes(SOURCE, {"anthropic_api_key": "synthetic"})

    def test_audio_file_cleanup_and_rejection(self):
        observed = []

        def fake(path):
            observed.append(Path(path))
            self.assertTrue(Path(path).exists())
            return {
                "content": SOURCE,
                "language": "en",
                "segments": [{"start": 0, "end": 4, "text": SOURCE}],
                "duration_seconds": 4,
            }

        with patch("pipeline_routes.transcribe_audio", side_effect=fake):
            response = self.client.post(
                "/api/pipeline/transcribe",
                data={
                    "title": "Demo recording",
                    "audio": (io.BytesIO(b"fake bounded audio"), "../../recording.wav"),
                },
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertFalse(observed[0].exists())
        stored = pipeline.transcript(response.json["id"])
        self.assertEqual(stored["origin"], "audio")
        self.assertEqual(json.loads(stored["segments_json"])[0]["start"], 0)
        for name, data in [("payload.exe", b"bad"), ("empty.wav", b"")]:
            self.assertEqual(
                self.client.post(
                    "/api/pipeline/transcribe",
                    data={"title": "x", "audio": (io.BytesIO(data), name)},
                ).status_code,
                400,
            )
        with patch(
            "pipeline_routes.transcribe_audio",
            side_effect=pipeline.PipelineError("Invalid audio", 422),
        ):
            self.assertEqual(
                self.client.post(
                    "/api/pipeline/transcribe",
                    data={"title": "x", "audio": (io.BytesIO(b"x"), "x.wav")},
                ).status_code,
                422,
            )

    def test_cross_origin_posts_and_unconfigured_audio(self):
        result = self.client.post(
            "/api/pipeline/import",
            headers={"Origin": "https://untrusted.invalid"},
            json={},
        )
        self.assertEqual(result.status_code, 403)
        with (
            patch.dict(os.environ, {"WHISPER_MODEL_PATH": ""}),
            self.assertRaises(pipeline.PipelineError) as result,
        ):
            audio_transcription.transcribe_audio("/unused")
        self.assertEqual(result.exception.status, 503)

    def test_migrations_are_repeatable(self):
        self.import_text()
        self.db.init_db()
        self.db.init_db()
        self.assertEqual(self.count("transcriptions"), 1)

    def test_legacy_transcript_survives_schema_upgrade(self):
        legacy_path = self.temp.name + "/legacy.db"
        with patch.object(self.db, "DB_PATH", legacy_path):
            with closing(self.db.get_db()) as db, db:
                db.execute("""CREATE TABLE transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, notion_page_id TEXT UNIQUE,
                    title TEXT NOT NULL, meeting_date TEXT, notion_url TEXT,
                    content TEXT, imported_at TEXT DEFAULT (datetime('now'))
                )""")
                db.execute(
                    "INSERT INTO transcriptions(notion_page_id,title,content) VALUES (?,?,?)",
                    ("invented-notion-id", "Existing import", SOURCE),
                )
            self.db.init_db()
            self.db.init_db()
            existing = pipeline.transcript(1)
            self.assertEqual(existing["content"], SOURCE)
            self.assertEqual(existing["origin"], "notion")
            self.assertIsNone(existing["source_hash"])
            saved = pipeline.save_draft(1, NOTES, "manual")
            self.assertEqual(saved["status"], "pending")
            self.assertEqual(self.count("meetings"), 0)
