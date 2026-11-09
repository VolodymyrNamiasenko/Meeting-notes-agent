import os
import tempfile
import unittest
from unittest.mock import patch, Mock

from parser import parse_meeting_notes
from notion_client import NotionClient
from clickup_client import ClickUpClient
from jira_client import JiraClient


class ParserTests(unittest.TestCase):
    def test_mixed_heading_levels(self):
        result = parse_meeting_notes("## Decisions\n- **[D1]** Ship it | Decided by: Team\n### Jira\n- **Title:** Bug\n- **Description:** Fix\n## Topics Internal\n1. **Build** — Test it")
        self.assertEqual(len(result["decisions"]), 1)
        self.assertEqual(result["jira_tickets"][0]["title"], "Bug")
        self.assertEqual(len(result["internal_topics"]), 1)

    def test_plain_heading_preserves_customer_internal(self):
        result = parse_meeting_notes("4. TOPICS TO DISCUSS — with Customer\n1. **Scope** — Agree\n5. TOPICS TO DISCUSS — Internal Team\n1. **Build** — Test")
        self.assertEqual(len(result["customer_topics"]), 1)
        self.assertEqual(len(result["internal_topics"]), 1)

    def test_clients_have_timeouts(self):
        response = Mock()
        response.json.return_value = {"results": [], "has_more": False}
        with patch("requests.get", return_value=response) as get, patch("requests.post", return_value=response) as post:
            NotionClient("test").get_page("page")
            NotionClient("test").list_database_pages("db")
            ClickUpClient("test").create_task("list", "name")
            JiraClient("email", "test", "example.atlassian.net").create_issue("TEST", "name")
        for call in get.call_args_list + post.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 30)

    def test_wsgi_startup_uses_isolated_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MEETING_DB_PATH": directory + "/test.db"}):
                import app
                import database
                with patch.object(database, "DB_PATH", directory + "/test.db"):
                    database.init_db()
                    client = app.app.test_client()
                    self.assertEqual(client.get("/").status_code, 200)
                    self.assertEqual(client.get("/meetings/999").status_code, 404)
                    self.assertEqual(client.get("/chat").status_code, 200)
                    self.assertNotEqual(app.app.secret_key, "meeting-manager-secret-key-change-me")


if __name__ == "__main__":
    unittest.main()
