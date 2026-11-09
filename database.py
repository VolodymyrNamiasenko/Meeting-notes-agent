import sqlite3
import os

DB_PATH = os.getenv("MEETING_DB_PATH", os.path.join(os.path.dirname(__file__), "meeting_manager.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notion_page_id TEXT UNIQUE,
            title TEXT NOT NULL,
            meeting_date TEXT,
            participants TEXT,
            notion_url TEXT,
            imported_at TEXT DEFAULT (datetime('now')),
            raw_content TEXT
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            decision_code TEXT,
            summary TEXT NOT NULL,
            decided_by TEXT,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS jira_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            resolved INTEGER DEFAULT 0,
            jira_issue_key TEXT,
            status TEXT DEFAULT 'pending',
            created_in_jira_at TEXT,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS clickup_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            clickup_task_id TEXT,
            status TEXT DEFAULT 'pending',
            created_in_clickup_at TEXT,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS customer_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            context TEXT,
            resolved INTEGER DEFAULT 0,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS internal_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            context TEXT,
            resolved INTEGER DEFAULT 0,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notion_page_id TEXT UNIQUE,
            title TEXT NOT NULL,
            meeting_date TEXT,
            notion_url TEXT,
            content TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'New Chat',
            meeting_ref TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS meeting_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription_id INTEGER NOT NULL REFERENCES transcriptions(id),
            notes_json TEXT NOT NULL, provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', version INTEGER NOT NULL DEFAULT 1,
            reviewer TEXT, meeting_id INTEGER REFERENCES meetings(id), reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS draft_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INTEGER NOT NULL REFERENCES meeting_drafts(id),
            action TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL,
            version INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    transcript_cols = {r[1] for r in conn.execute('PRAGMA table_info(transcriptions)')}
    for name, sql in {'origin': "TEXT DEFAULT 'notion'", 'source_hash': 'TEXT', 'language': 'TEXT', 'segments_json': 'TEXT'}.items():
        if name not in transcript_cols:conn.execute(f'ALTER TABLE transcriptions ADD COLUMN {name} {sql}')
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS transcript_source ON transcriptions(source_hash,title,COALESCE(meeting_date,'')) WHERE source_hash IS NOT NULL")
    conn.commit()

    # Migrations for existing databases
    cursor = conn.execute("PRAGMA table_info(jira_tickets)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    migrations = {
        "jira_issue_key": "ALTER TABLE jira_tickets ADD COLUMN jira_issue_key TEXT",
        "status": "ALTER TABLE jira_tickets ADD COLUMN status TEXT DEFAULT 'pending'",
        "created_in_jira_at": "ALTER TABLE jira_tickets ADD COLUMN created_in_jira_at TEXT",
    }
    for col, sql in migrations.items():
        if col not in existing_cols:
            conn.execute(sql)
    conn.commit()

    # Migration: add meeting_ref to chat_sessions if missing
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "chat_sessions" in tables:
        cursor = conn.execute("PRAGMA table_info(chat_sessions)")
        session_cols = {row[1] for row in cursor.fetchall()}
        if "meeting_ref" not in session_cols:
            try:
                conn.execute("ALTER TABLE chat_sessions ADD COLUMN meeting_ref TEXT")
            except Exception:
                pass
    conn.commit()

    conn.close()
