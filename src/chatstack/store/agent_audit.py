from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any


DB_PATH = Path("./data/agent_audit.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    backend TEXT,
    tokens_in INT,
    tokens_out INT,
    approx_cost REAL,
    user_prompt TEXT,
    assistant_content TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    # Ensure directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(SCHEMA)
    return conn


def insert_agent_request(
    backend: str,
    tokens_in: Optional[int],
    tokens_out: Optional[int],
    approx_cost: Optional[float],
    user_prompt: str,
    assistant_content: str,
) -> None:
    conn = _get_conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO agent_requests(backend, tokens_in, tokens_out, approx_cost, user_prompt, assistant_content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (backend, tokens_in, tokens_out, approx_cost, user_prompt, assistant_content),
            )
    finally:
        conn.close()


def list_agent_requests(limit: int = 10) -> List[Dict[str, Any]]:
    """Return last `limit` rows ordered by id desc from agent_requests table."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            SELECT id, timestamp, backend, tokens_in, tokens_out, approx_cost, user_prompt, assistant_content
            FROM agent_requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
        result: List[Dict[str, Any]] = [dict(zip(columns, row)) for row in rows]
        return result
    finally:
        conn.close()
