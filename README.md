# Meeting Manager

A local web app that pulls structured meeting notes from Notion, parses them into actionable items, and lets you manage decisions, tickets, and discussion topics across all your meetings.

## Features

- **Notion sync** — fetches meeting notes from a Notion database
- **Auto-parsing** — extracts decisions, JIRA tickets, ClickUp tickets, and discussion topics from your structured notes
- **Consolidated views** — browse all decisions, tickets, and topics across meetings with search and filters
- **ClickUp integration** — push internal tickets directly to a ClickUp list with one click
- **Copy-to-clipboard** — one-click copy for JIRA tickets (title + description) and discussion topics
- **Topic tracking** — mark customer/internal discussion topics as resolved
- **Meeting history** — browse and re-sync individual meetings

## Setup

### 1. Install dependencies

```bash
cd meeting-manager
pip install -r requirements.txt
```

### 2. Set up Notion

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create a new integration → copy the API token
3. Open your meeting notes database in Notion
4. Click `•••` → "Connections" → add your integration
5. Copy the database ID from the URL: `notion.so/<workspace>/<DATABASE_ID>?v=...`

### 3. Run the app

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

### 4. Configure

1. Go to **Settings** in the sidebar
2. Paste your Notion API token and database ID
3. (Optional) Add your ClickUp API token and list ID
4. Click **Save**

### 5. Sync

Click **"Sync from Notion"** on the Dashboard. The app will:
- Fetch all pages from your Notion database
- Parse each page's structured meeting notes
- Store all items in the local SQLite database
- Skip pages that were already imported

## Meeting Notes Format

Your Notion pages must follow this structure (with `###` headings):

```
### 1. DECISIONS LOG
- **[DECISION-001]** Summary | Decided by: Name1, Name2

### 2. JIRA TICKETS — for Customer Team
- **Title:** Action item title
- **Description:** What needs to be done

### 3. CLICKUP TICKETS — for Internal Dev Team
- **Title:** Action item title
- **Description:** What needs to be done

### 4. TOPICS TO DISCUSS — with Customer
1. **Topic** — Context

### 5. TOPICS TO DISCUSS — Internal Team
1. **Topic** — Context
```

## File Structure

```
meeting-manager/
├── app.py              # Flask web server + API routes
├── database.py         # SQLite schema and connection
├── parser.py           # Markdown meeting notes parser
├── notion_client.py    # Notion API integration
├── clickup_client.py   # ClickUp API integration
├── config.json         # Your API tokens (auto-created, gitignore this)
├── meeting_manager.db  # SQLite database (auto-created)
├── requirements.txt
├── README.md
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── meetings.html
    ├── meeting_detail.html
    ├── decisions.html
    ├── jira.html
    ├── clickup.html
    ├── topics.html
    └── settings.html
```

## Tips

- **Re-sync a meeting**: Click the ↻ button on any meeting to re-fetch from Notion (useful if you edited notes)
- **Copy all open topics**: Use the "Copy all open" button on the Topics page to prepare your meeting agenda
- **Search**: Every list page has a search bar that filters items in real-time
- Add `config.json` to your `.gitignore` — it contains your API tokens
