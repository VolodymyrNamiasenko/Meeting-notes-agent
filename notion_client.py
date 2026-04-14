import requests
import json
import re

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def list_database_pages(self, database_id: str, start_cursor: str = None) -> dict:
        """Fetch pages from a Notion database."""
        url = f"{NOTION_API_URL}/databases/{database_id}/query"
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_all_database_pages(self, database_id: str) -> list:
        """Fetch all pages from a database, handling pagination."""
        all_pages = []
        cursor = None

        while True:
            data = self.list_database_pages(database_id, cursor)
            all_pages.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return all_pages

    def get_page(self, page_id: str) -> dict:
        """Get page metadata."""
        url = f"{NOTION_API_URL}/pages/{page_id}"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_page_blocks(self, page_id: str) -> list:
        """Get all blocks (content) from a page."""
        all_blocks = []
        cursor = None

        while True:
            url = f"{NOTION_API_URL}/blocks/{page_id}/children?page_size=100"
            if cursor:
                url += f"&start_cursor={cursor}"

            resp = requests.get(url, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            all_blocks.extend(data.get("results", []))

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return all_blocks

    def blocks_to_markdown(self, blocks: list) -> str:
        """Convert Notion blocks to markdown text."""
        lines = []
        for block in blocks:
            block_type = block.get("type", "")
            block_data = block.get(block_type, {})

            if block_type == "heading_1":
                text = self._extract_rich_text(block_data.get("rich_text", []))
                lines.append(f"# {text}")
            elif block_type == "heading_2":
                text = self._extract_rich_text(block_data.get("rich_text", []))
                lines.append(f"## {text}")
            elif block_type == "heading_3":
                text = self._extract_rich_text(block_data.get("rich_text", []))
                lines.append(f"### {text}")
            elif block_type == "paragraph":
                text = self._extract_rich_text(block_data.get("rich_text", []))
                lines.append(text)
            elif block_type == "bulleted_list_item":
                text = self._extract_rich_text(block_data.get("rich_text", []))
                lines.append(f"- {text}")
            elif block_type == "numbered_list_item":
                text = self._extract_rich_text(block_data.get("rich_text", []))
                lines.append(f"1. {text}")
            elif block_type == "divider":
                lines.append("---")
            elif block_type == "toggle":
                text = self._extract_rich_text(block_data.get("rich_text", []))
                lines.append(f"- {text}")
            else:
                # Fallback: try to extract any rich_text
                if "rich_text" in block_data:
                    text = self._extract_rich_text(block_data["rich_text"])
                    if text:
                        lines.append(text)

        return "\n".join(lines)

    def _extract_rich_text(self, rich_text_array: list) -> str:
        """Extract plain text from Notion rich_text array, preserving bold markers."""
        parts = []
        for rt in rich_text_array:
            text = rt.get("plain_text", "")
            annotations = rt.get("annotations", {})
            if annotations.get("bold"):
                text = f"**{text}**"
            parts.append(text)
        return "".join(parts)

    def get_page_title(self, page: dict) -> str:
        """Extract the title from a page's properties."""
        props = page.get("properties", {})
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "title":
                title_parts = prop_data.get("title", [])
                return "".join(t.get("plain_text", "") for t in title_parts)
        return "Untitled"

    def get_page_date(self, page: dict) -> str:
        """Try to extract a date property from the page."""
        props = page.get("properties", {})
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "date" and prop_data.get("date"):
                return prop_data["date"].get("start", "")
        # Fallback to created_time
        return page.get("created_time", "")[:10]

    def get_page_url(self, page: dict) -> str:
        """Get the Notion URL for a page."""
        return page.get("url", "")
