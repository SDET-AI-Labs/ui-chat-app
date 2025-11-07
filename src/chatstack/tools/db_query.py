from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List
import asyncio

import logging
logger = logging.getLogger("db_query")


def _is_select_query(q: str) -> bool:
    if not isinstance(q, str):
        return False
    s = q.strip().lstrip("; ").strip()
    # Very simple guard: only allow plain SELECT to run
    return s[:6].lower() == "select"


def _sqlite_query(conn_str: str, query: str) -> List[Dict[str, Any]]:
    con = sqlite3.connect(conn_str)
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        # Convert to list of dicts
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({k: r[k] for k in r.keys()})
        return out
    finally:
        con.close()


def _postgres_query(conn_str: str, query: str) -> List[Dict[str, Any]]:
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import RealDictCursor  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("psycopg2 not installed") from e

    con = psycopg2.connect(conn_str)
    try:
        cur = con.cursor(cursor_factory=RealDictCursor)
        cur.execute(query)
        rows = cur.fetchall()
        # rows already mapping-like
        return [dict(r) for r in rows]
    finally:
        con.close()


async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        query = args.get("query") if isinstance(args, dict) else None
        logger.info(f"db_query: received query: {query!r}")
        if not isinstance(query, str) or not query.strip():
            logger.error("db_query: query must be a non-empty string")
            return {"result": "error", "error": "query must be a non-empty string"}
        if not _is_select_query(query):
            logger.error("db_query: only SELECT queries are allowed")
            return {"result": "error", "error": "only SELECT queries are allowed"}

        kind = os.environ.get("DB_KIND", "sqlite").strip().lower()
        conn_str = os.environ.get("DB_STRING")
        logger.info(f"db_query: DB_KIND={kind}, DB_STRING={conn_str}")
        if not conn_str:
            logger.error("db_query: DB_STRING env not set")
            return {"result": "error", "error": "DB_STRING env not set"}

        if kind == "sqlite":
            try:
                rows = await asyncio.to_thread(_sqlite_query, conn_str, query)
                logger.info(f"db_query: sqlite returned {len(rows)} rows")
                return {"result": rows}
            except Exception as e:
                logger.error(f"db_query: sqlite error: {e}")
                return {"result": "error", "error": str(e)}
        elif kind == "postgres":
            try:
                rows = await asyncio.to_thread(_postgres_query, conn_str, query)
                logger.info(f"db_query: postgres returned {len(rows)} rows")
                return {"result": rows}
            except RuntimeError as e:
                logger.error(f"db_query: postgres runtime error: {e}")
                return {"result": "error", "error": str(e)}
            except Exception as e:
                logger.error(f"db_query: postgres error: {e}")
                return {"result": "error", "error": str(e)}
        else:
            logger.error(f"db_query: unsupported DB_KIND: {kind}")
            return {"result": "error", "error": f"unsupported DB_KIND: {kind}"}
    except Exception as e:  # noqa: BLE001
        logger.error(f"db_query: unexpected error: {e}")
        return {"result": "error", "error": str(e)}
