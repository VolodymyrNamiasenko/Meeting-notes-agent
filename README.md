# Meeting Notes Manager · Personal workflow

A local Flask/SQLite application for reviewing structured meeting notes and transcripts imported from Notion. It connects a personal AI-assisted meeting workflow to searchable decisions, discussion topics and human-triggered Jira/ClickUp task creation.

## Where this app fits

1. **Upstream, outside this repository:** record/transcribe a meeting (for example with Sembly AI) and prepare structured notes in a Notion database. This app does not record audio, transcribe it or call a Sembly API.
2. **Inside this repository:** import notes/transcripts from configured Notion databases; parse decisions, ticket drafts and topics into SQLite.
3. **Human review:** inspect the imported drafts and source meeting before choosing to create a Jira subtask or ClickUp task. Synchronizing notes does not automatically create remote tickets.
4. **Optional Claude chat:** send a question and selected/recent transcript context to Anthropic. Review the response against the original transcript.

The supported workflow is personal tooling, distinct from a professional ERP/MES support pilot. The repository does not contain client meeting records or pilot results. See [capability evidence and a synthetic walkthrough](docs/PORTFOLIO.md).

## Features

- Import and resynchronize notes from a shared Notion database.
- Parse structured Markdown, including mixed heading levels.
- Browse meeting history, decisions, topics, transcripts and activity statistics.
- Draft or create Jira/ClickUp items from the interface.
- Ask Claude questions using imported transcript context, with persisted local chat sessions.

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

In Settings, configure your Notion token and notes database ID; configure a separate transcriptions database ID to import transcripts. The integration must be explicitly connected to both databases. The client uses Notion API version `2022-06-28` and its database-query endpoint; live compatibility and permissions must be checked with your own integration, especially for newer multi-source database setups.

Jira and ClickUp credentials are optional; verify the Jira parent key and ClickUp list before creating items. Anthropic chat is optional and requires an API key; API usage may incur charges. Chat uses `claude-sonnet-4-20250514` by default, configurable through `ANTHROPIC_MODEL`. Availability depends on your account. There is no local Ollama inference in this app.

No credentials are needed to start the empty app, browse its pages or run the mocked tests. For a safe walkthrough, put [the invented notes](examples/synthetic_meeting_notes.md) in a test Notion page and follow `docs/PORTFOLIO.md`. Do not use client data to demonstrate the public repository.

`config.json` contains credentials, and `meeting_manager.db` contains private notes/transcripts. Keep both out of Git and back them up privately. `MEETING_DB_PATH` can select another database.

When chat context is enabled, transcript text leaves your computer for the Anthropic API; chat history is sent too. Up to 80,000 characters of context may be selected and long transcripts may be truncated or omitted. Only use data you are authorized to send. The app does not write full API payloads to debug files or print transcript titles/message excerpts by default. Chat content still persists locally in SQLite.

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
