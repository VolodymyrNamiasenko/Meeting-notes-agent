import requests
from base64 import b64encode


JIRA_API_URL = "https://{domain}/rest/api/3"


class JiraClient:
    def __init__(self, email: str, api_token: str, domain: str):
        self.domain = domain
        credentials = b64encode(f"{email}:{api_token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }
        self.base_url = JIRA_API_URL.format(domain=domain)

    def create_issue(self, project_key: str, summary: str, description: str = "", issue_type: str = "Task") -> dict:
        """Create an issue in a Jira project."""
        url = f"{self.base_url}/issue"
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}] if description else []
                        }
                    ]
                },
                "issuetype": {"name": issue_type},
            }
        }
        resp = requests.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_issue_url(self, issue_key: str) -> str:
        """Build the browse URL for an issue."""
        return f"https://{self.domain}/browse/{issue_key}"
