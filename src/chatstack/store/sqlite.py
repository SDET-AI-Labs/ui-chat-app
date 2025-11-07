import sqlite3
from pathlib import Path
from typing import Iterable, Tuple, List

DB_PATH = Path(".chatstack.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(SCHEMA)
    return conn

def append_messages(session_id: str, pairs: Iterable[Tuple[str, str]]):
    conn = get_conn()
    with conn:
        conn.executemany(
            "INSERT INTO transcripts(session_id, role, content) VALUES (?, ?, ?)",
            [(session_id, role, content) for role, content in pairs]
        )
    conn.close()

def load_session(session_id: str) -> List[Tuple[str, str, str]]:
    conn = get_conn()
    cur = conn.execute(
        "SELECT role, content, ts FROM transcripts WHERE session_id=? ORDER BY ts ASC",
        (session_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows
