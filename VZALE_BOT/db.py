"""Shared database helpers for both the bot and the HTTP API."""
from __future__ import annotations

import sqlite3
from typing import Optional

import aiosqlite
import bcrypt

from config import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """Return a sqlite3 connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


async def get_team_by_code(code: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT team_name FROM team_security WHERE invite_code = ?",
            (code.strip().upper(),),
        )
        row = await cur.fetchone()
        return row[0] if row else None


def set_web_user(telegram_id: int, username: str, password: str) -> None:
    """Create or update web credentials for the Telegram user."""
    conn = get_db_connection()
    cur = conn.cursor()
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cur.execute(
        """
        INSERT INTO web_users (telegram_id, username, password_hash)
        VALUES (?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
          username = excluded.username,
          password_hash = excluded.password_hash
        """,
        (telegram_id, username, pw_hash),
    )
    conn.commit()
    conn.close()


async def get_user_by_telegram_id(telegram_id: int) -> Optional[dict]:
    """Return user fields by telegram_id or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
