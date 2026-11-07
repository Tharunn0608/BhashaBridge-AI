"""Stores and loads conversation history in SQLite (text only)."""
from datetime import datetime, timezone

from database.db import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def add(self, session_id, role, content, language=None, source=None) -> str:
        created = _now()
        conn = connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, language, source, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, role, content, language, source, created),
                )
        finally:
            conn.close()
        return created

    def history(self, session_id, limit=50):
        """Oldest-first list of the most recent `limit` messages."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT role, content, language, source, created_at FROM messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in reversed(rows)]

    def clear(self, session_id) -> int:
        conn = connect(self.db_path)
        try:
            with conn:
                cur = conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            return cur.rowcount
        finally:
            conn.close()
