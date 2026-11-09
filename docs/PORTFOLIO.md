# Capability evidence and safe walkthrough

| Workflow capability | Code evidence | Boundary |
| --- | --- | --- |
| Notion notes/transcript import | `notion_client.py`, sync routes in `app.py` | Requires existing pages and a connected integration; top-level supported block text only |
| Structured decisions and drafts | `parser.py`, `database.py` | Rule-based Markdown parsing, not automatic AI note generation |
| Human-triggered delivery | Jira/ClickUp routes and review pages | Import creates local pending drafts; remote writes require a separate user action |
| Transcript question answering | Claude Messages request in `app.py` | Sends context/history to Anthropic when requested |
| Local audio transcription | `audio_transcription.py`, pipeline upload route and Import and review page | Optional faster-whisper dependency and a preinstalled local model; bounded files/duration, no audio recorder or Sembly API |
| Grounded AI note drafts | `meeting_pipeline.py` and pipeline routes | Explicit Claude consent; schema and exact-quote validation; semantic meaning still needs review |
| Draft review | Versioned draft edits, decisions and event history | Approval creates only local pending tasks; reviewer names are self-reported, not authenticated identities |

The combined portfolio stack spans multiple projects: this app uses Python, Flask, SQLite/SQL, Notion API and optional Claude; FastAPI, Ollama and Chroma belong to the separate support assistant. A public repository is not evidence of professional pilot outcomes.

## Reproducible local checks

Install `requirements.txt`, then run `python -m unittest discover -s tests -v`. Tests use temporary SQLite databases and mocks; they do not read local credentials, contact live services, create paid chat requests or create remote tasks.

## Optional manual walkthrough

1. Start the empty local app with `python app.py`; visit the dashboard, settings, meetings, decisions, topics and chat pages.
2. Put `examples/synthetic_meeting_notes.md` in a **test** Notion page. Use native Notion headings and rich-text bold formatting corresponding to the example, not a single code block.
3. Connect the integration to the test database, configure its ID privately and sync. Check that all five sections appear and ticket drafts remain pending. Syncing again should skip an already imported page.
4. Review the drafts. If testing delivery, configure a disposable Jira parent/ClickUp list and explicitly create one item. Confirm the destination and returned identifier before continuing. Cancelled or already-created drafts must not be sent again by the app.
5. If testing chat, import an invented transcript from the separate transcript database. Explicitly enable context only for text permitted to leave your machine. Confirm the referenced meeting/date and any truncation warning; verify the answer manually.

Record permissions, API versions, observed results and date. Automated mocks do not establish live integration compatibility or model quality. No live service acceptance results are claimed here. See `EVALUATION.md` for evaluation guidance and the README for local-only security limits.
