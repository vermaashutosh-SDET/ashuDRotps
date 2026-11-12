import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).resolve().parent.parent / "otps.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                sender_name TEXT,
                sender_email TEXT,
                service_tag TEXT,
                subject TEXT,
                otp_code TEXT,
                verification_link TEXT,
                snippet TEXT,
                body_text TEXT,
                body_html TEXT,
                received_at TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_id ON otps(message_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON otps(created_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_received_at ON otps(received_at DESC);")
        conn.commit()

def is_message_seen(message_id: str) -> bool:
    if not message_id:
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM otps WHERE message_id = ?", (message_id,))
        return cursor.fetchone() is not None

def insert_otp(
    message_id: str,
    sender_name: str,
    sender_email: str,
    service_tag: str,
    subject: str,
    otp_code: Optional[str],
    verification_link: Optional[str],
    snippet: str,
    body_text: str,
    body_html: str,
    received_at: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    if not received_at:
        received_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO otps (
                    message_id, sender_name, sender_email, service_tag,
                    subject, otp_code, verification_link, snippet,
                    body_text, body_html, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id, sender_name, sender_email, service_tag,
                subject, otp_code, verification_link, snippet,
                body_text, body_html, received_at
            ))
            conn.commit()
            inserted_id = cursor.lastrowid
            return get_otp_by_id(inserted_id)
        except sqlite3.IntegrityError:
            # Duplicate message_id
            return None

def get_otps(limit: int = 50, search: Optional[str] = None, service: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT id, message_id, sender_name, sender_email, service_tag, subject, otp_code, verification_link, snippet, received_at, created_at FROM otps WHERE 1=1"
        params = []

        if service and service.lower() != "all":
            s_pattern = f"%{service.strip().lower()}%"
            query += " AND (LOWER(service_tag) LIKE ? OR LOWER(sender_name) LIKE ? OR LOWER(sender_email) LIKE ? OR LOWER(subject) LIKE ?)"
            params.extend([s_pattern, s_pattern, s_pattern, s_pattern])

        if search:
            search_pattern = f"%{search.strip().lower()}%"
            query += " AND (LOWER(subject) LIKE ? OR LOWER(sender_name) LIKE ? OR LOWER(sender_email) LIKE ? OR LOWER(otp_code) LIKE ? OR LOWER(snippet) LIKE ?)"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern, search_pattern])

        query += " ORDER BY received_at DESC, id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_otp_by_id(otp_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM otps WHERE id = ?", (otp_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_latest_otp(service: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM otps WHERE otp_code IS NOT NULL AND otp_code != ''"
        params = []
        if service and service.lower() != "all":
            s_pattern = f"%{service.strip().lower()}%"
            query += " AND (LOWER(service_tag) LIKE ? OR LOWER(sender_name) LIKE ? OR LOWER(sender_email) LIKE ? OR LOWER(subject) LIKE ?)"
            params.extend([s_pattern, s_pattern, s_pattern, s_pattern])

        query += " ORDER BY received_at DESC, id DESC LIMIT 1"
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_otp(otp_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM otps WHERE id = ?", (otp_id,))
        conn.commit()
        return cursor.rowcount > 0

def clear_all_otps() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM otps")
        count = cursor.rowcount
        conn.commit()
        return count
