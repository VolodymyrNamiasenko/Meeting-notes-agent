# Meeting Manager

A local Flask application for organizing Notion meeting notes and transcripts into decisions, Jira/ClickUp tickets, and customer/internal discussion topics.

## Features

- Import and resynchronize notes from a shared Notion database.
- Parse structured Markdown, including mixed heading levels.
- Browse meeting history, decisions, topics, transcripts and activity statistics.
- Draft or create Jira/ClickUp items from the interface.
- Search transcript content through a configurable local model workflow.

Statistics and generated answers depend on imported data quality; they are not independently verified summaries.

## Setup

Requires Python 3.11+. Run from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5001. Set `PORT` to change it. Debug mode is off unless `FLASK_DEBUG=1`. Set a private, stable `FLASK_SECRET_KEY` if sessions should survive restarts or multiple server instances.

In Settings, configure your Notion token and database ID. The integration must be explicitly connected to the database. Jira and ClickUp credentials are optional; verify their target project/list before creating items. API requests have bounded timeouts.

`config.json` contains credentials, and `meeting_manager.db` contains private notes/transcripts. Keep both out of Git and back them up privately. `MEETING_DB_PATH` can select another database.

## Notes format

```markdown
### 1. DECISIONS LOG
- **[DECISION-001]** Summary | Decided by: Team

### 2. JIRA TICKETS — for Customer Team
- **Title:** Action title
- **Description:** Required change

### 3. CLICKUP TICKETS — for Internal Dev Team
- **Title:** Internal task
- **Description:** Expected outcome

### 4. TOPICS TO DISCUSS — with Customer
1. **Scope** — Context

### 5. TOPICS TO DISCUSS — Internal Team
1. **Build** — Context
```

## Checks

```bash
python -m unittest discover -s tests -v
```

Tests mock external services and create an isolated database. They do not create live tickets or modify Notion.

## Deployment limits

This is a local single-user tool, not a public service. There is no user-account authorization layer or complete CSRF protection. A randomly generated fallback secret prevents the old known-secret issue, but does not replace access controls. Do not expose the development server or private settings to the internet.

Sync parsers and LLM answers need representative, human-reviewed evaluation. Live permissions, remote API compatibility and rate-limit behavior remain separate acceptance checks. See [evaluation guidance](docs/EVALUATION.md).
