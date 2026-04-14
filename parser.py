import re


def parse_meeting_notes(content: str) -> dict:
    """
    Parse structured meeting notes markdown into sections.
    Expects the 5-section format: Decisions, JIRA Tickets, ClickUp Tickets,
    Customer Topics, Internal Topics.
    """
    result = {
        "decisions": [],
        "jira_tickets": [],
        "clickup_tickets": [],
        "customer_topics": [],
        "internal_topics": [],
    }

    sections = _split_sections(content)

    for header, body in sections:
        header_lower = header.lower()
        if "decision" in header_lower:
            result["decisions"] = _parse_decisions(body)
        elif "jira" in header_lower:
            result["jira_tickets"] = _parse_tickets(body)
        elif "clickup" in header_lower:
            result["clickup_tickets"] = _parse_tickets(body)
        elif "customer" in header_lower or ("topic" in header_lower and "internal" not in header_lower):
            result["customer_topics"] = _parse_topics(body)
        elif "internal" in header_lower:
            result["internal_topics"] = _parse_topics(body)

    return result


def _split_sections(content: str) -> list:
    """Split markdown content by heading markers into (header, body) pairs.
    Handles ###, ##, # and also Notion-style headings without markdown markers.
    """
    # Try ### first, then ## then #
    for marker in [r"^###\s+", r"^##\s+", r"^#\s+"]:
        pattern = marker + r"(.+?)$"
        parts = re.split(pattern, content, flags=re.MULTILINE)
        if len(parts) > 1:
            sections = []
            for i in range(1, len(parts), 2):
                header = parts[i].strip()
                body = parts[i + 1].strip() if i + 1 < len(parts) else ""
                sections.append((header, body))
            return sections

    # Fallback: look for numbered section headers like "1. DECISIONS LOG"
    pattern = r"^\d+\.\s+(DECISIONS|JIRA|CLICKUP|TOPICS).+$"
    parts = re.split(pattern, content, flags=re.MULTILINE | re.IGNORECASE)
    if len(parts) > 1:
        sections = []
        for i in range(1, len(parts), 2):
            header = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append((header, body))
        return sections

    return []


def _parse_decisions(body: str) -> list:
    """
    Parse decision entries like:
    - **[DECISION-001]** Summary text | Decided by: Name1, Name2
    """
    decisions = []
    pattern = r"-\s+\*\*\[([^\]]+)\]\*\*\s+(.+?)(?:\|\s*Decided by:\s*(.+))?$"

    for line in body.split("\n"):
        line = line.strip()
        match = re.match(pattern, line)
        if match:
            decisions.append({
                "code": match.group(1).strip(),
                "summary": match.group(2).strip().rstrip("|").strip(),
                "decided_by": match.group(3).strip() if match.group(3) else "",
            })

    return decisions


def _parse_tickets(body: str) -> list:
    """
    Parse ticket entries like:
    - **Title:** Some title
    - **Description:** Some description
    """
    tickets = []
    current_ticket = {}

    for line in body.split("\n"):
        line = line.strip()

        title_match = re.match(r"-?\s*\*\*Title:\*\*\s*(.+)", line)
        desc_match = re.match(r"-?\s*\*\*Description:\*\*\s*(.+)", line)

        if title_match:
            if current_ticket.get("title"):
                tickets.append(current_ticket)
            current_ticket = {"title": title_match.group(1).strip(), "description": ""}
        elif desc_match:
            current_ticket["description"] = desc_match.group(1).strip()

    if current_ticket.get("title"):
        tickets.append(current_ticket)

    return tickets


def _parse_topics(body: str) -> list:
    """
    Parse numbered topic entries like:
    1. **Topic title** — Context description
    or
    1. Topic title — Context description
    """
    topics = []
    pattern = r"^\d+\.\s+\*?\*?(.+?)(?:\*\*)?(?:\s*[—\-–]\s*)(.+)$"

    for line in body.split("\n"):
        line = line.strip()
        match = re.match(pattern, line)
        if match:
            topic = match.group(1).strip().rstrip("*").strip()
            context = match.group(2).strip()
            topics.append({"topic": topic, "context": context})

    return topics
