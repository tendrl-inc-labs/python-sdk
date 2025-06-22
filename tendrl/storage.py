import sqlite3
import threading
import time
import json
from typing import Dict, Any


class SQLiteStorage:
    """Simple SQLite storage for offline message buffering."""

    def __init__(self, db_path: str = "tendrl_storage.db"):
        """Initialize SQLite storage.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._conn = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    tags TEXT,
                    expires_at INTEGER NOT NULL
                )
            """)
            
            # Single index for cleanup
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at 
                ON messages(expires_at)
            """)

    def _get_conn(self):
        """Get or create SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def store(self, msg_id: str, data: Dict[str, Any], tags: list = None, ttl: int = 3600):
        """Store a message with TTL.

        Args:
            msg_id: Unique message identifier
            data: Message data to store
            tags: Optional tags for webhook processing
            ttl: Time-to-live in seconds
        """
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?)",
                    (msg_id, json.dumps(data), json.dumps(tags) if tags else None, int(time.time()) + ttl),
                )

    def get_all_messages(self, limit: int = None) -> list:
        """Retrieve all non-expired messages.

        Args:
            limit: Optional limit on number of messages to retrieve

        Returns:
            list: List of stored messages
        """
        with self._lock:
            with self._get_conn() as conn:
                current_time = int(time.time())
                
                if limit:
                    rows = conn.execute(
                        "SELECT * FROM messages WHERE expires_at >= ? ORDER BY id LIMIT ?",
                        (current_time, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM messages WHERE expires_at >= ? ORDER BY id",
                        (current_time,)
                    ).fetchall()
                    
                return [dict(row) for row in rows]

    def delete_messages(self, msg_ids: list):
        """Delete messages by their IDs.

        Args:
            msg_ids: List of message IDs to delete
        """
        if not msg_ids:
            return
            
        with self._lock:
            with self._get_conn() as conn:
                placeholders = ",".join("?" * len(msg_ids))
                conn.execute(
                    f"DELETE FROM messages WHERE id IN ({placeholders})",
                    msg_ids
                )

    def get_message_count(self) -> int:
        """Get count of non-expired messages.

        Returns:
            int: Number of active messages
        """
        with self._lock:
            with self._get_conn() as conn:
                current_time = int(time.time())
                row = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE expires_at >= ?", 
                    (current_time,)
                ).fetchone()
                return row[0] if row else 0

    def cleanup_expired(self) -> int:
        """Remove expired messages.
        
        Returns:
            int: Number of messages deleted
        """
        with self._lock:
            with self._get_conn() as conn:
                result = conn.execute(
                    "DELETE FROM messages WHERE expires_at < ?",
                    (int(time.time()),),
                )
                return result.rowcount

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
