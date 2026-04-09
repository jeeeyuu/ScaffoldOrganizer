import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_cache (
        id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        summary TEXT,
        notion_markdown_table TEXT,
        raw_output TEXT,
        markdown_output TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        priority TEXT NOT NULL,
        category TEXT NOT NULL,
        task TEXT NOT NULL,
        next_action TEXT NOT NULL,
        tool TEXT,
        estimate_min INTEGER,
        status TEXT NOT NULL,
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_usage_logs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        response_id TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        total_tokens INTEGER,
        raw_usage_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
]


def init_db(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        _ensure_columns(conn)
        conn.commit()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "raw_output" not in existing:
        conn.execute("ALTER TABLE sessions ADD COLUMN raw_output TEXT")
    if "markdown_output" not in existing:
        conn.execute("ALTER TABLE sessions ADD COLUMN markdown_output TEXT")


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def upsert_prompt_cache(conn: sqlite3.Connection, prompt_id: str, content: str, updated_at: str) -> None:
    conn.execute(
        "INSERT INTO prompt_cache (id, content, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at",
        (prompt_id, content, updated_at),
    )


def get_prompt_cache(conn: sqlite3.Connection, prompt_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM prompt_cache WHERE id = ?", (prompt_id,)).fetchone()


def insert_session(
    conn: sqlite3.Connection,
    session_id: str,
    title: str,
    created_at: str,
    summary: str | None = None,
    notion_markdown_table: str | None = None,
    raw_output: str | None = None,
    markdown_output: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO sessions (id, title, created_at, summary, notion_markdown_table, raw_output, markdown_output) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, title, created_at, summary, notion_markdown_table, raw_output, markdown_output),
    )


def upsert_session(
    conn: sqlite3.Connection,
    session_id: str,
    title: str,
    created_at: str,
    summary: str | None = None,
    notion_markdown_table: str | None = None,
    raw_output: str | None = None,
    markdown_output: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO sessions (id, title, created_at, summary, notion_markdown_table, raw_output, markdown_output) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET title = excluded.title, created_at = excluded.created_at, "
        "summary = excluded.summary, notion_markdown_table = excluded.notion_markdown_table, "
        "raw_output = excluded.raw_output, markdown_output = excluded.markdown_output",
        (session_id, title, created_at, summary, notion_markdown_table, raw_output, markdown_output),
    )


def insert_message(
    conn: sqlite3.Connection,
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (message_id, session_id, role, content, created_at),
    )


def delete_messages_for_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))


def delete_tasks_for_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM tasks WHERE session_id = ?", (session_id,))


def insert_task(conn: sqlite3.Connection, session_id: str, task_data: dict) -> None:
    conn.execute(
        """
        INSERT INTO tasks (
            id, session_id, priority, category, task, next_action, tool, estimate_min, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_data["id"],
            session_id,
            task_data["priority"],
            task_data["category"],
            task_data["task"],
            task_data["next_action"],
            task_data.get("tool"),
            task_data.get("estimate_min"),
            task_data["status"],
            task_data.get("notes"),
        ),
    )


def insert_usage_log(
    conn: sqlite3.Connection,
    log_id: str,
    session_id: str,
    response_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    raw_usage_json: str | None,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO api_usage_logs (
            id, session_id, response_id, input_tokens, output_tokens, total_tokens, raw_usage_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            session_id,
            response_id,
            input_tokens,
            output_tokens,
            total_tokens,
            raw_usage_json,
            created_at,
        ),
    )

def load_tasks(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM tasks WHERE session_id = ?", (session_id,)).fetchall()
    return [dict(row) for row in rows]


def list_sessions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def load_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
    return [dict(row) for row in rows]
