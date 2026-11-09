import requests


CLICKUP_API_URL = "https://api.clickup.com/api/v2"


class ClickUpClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json",
        }

    def create_task(self, list_id: str, name: str, description: str = "") -> dict:
        """Create a task in a ClickUp list."""
        url = f"{CLICKUP_API_URL}/list/{list_id}/task"
        payload = {
            "name": name,
            "description": description,
            "status": "to do",
        }
        resp = requests.post(url, headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_lists(self, folder_id: str) -> list:
        """Get lists in a folder."""
        url = f"{CLICKUP_API_URL}/folder/{folder_id}/list"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("lists", [])

    def get_spaces(self, team_id: str) -> list:
        """Get spaces in a workspace."""
        url = f"{CLICKUP_API_URL}/team/{team_id}/space"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("spaces", [])

    def get_teams(self) -> list:
        """Get workspaces (teams)."""
        url = f"{CLICKUP_API_URL}/team"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("teams", [])
