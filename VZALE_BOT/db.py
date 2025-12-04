"""Shared database helpers for both the bot and the HTTP API."""
from __future__ import annotations

import sqlite3
from typing import Optional

import aiosqlite
import bcrypt
import json

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


async def _table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    """Check if a table exists in the current SQLite database."""
    cur = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    row = await cur.fetchone()
    return bool(row)


async def get_all_tournaments() -> list[dict]:
    """Return all tournaments or an empty list when the table is missing/empty."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if not await _table_exists(db, "tournaments"):
            return []

        cur = await db.execute(
            "SELECT id, name, status, date_start, venue, settings_json FROM tournaments"
        )
        rows = await cur.fetchall()

        tournaments: list[dict] = []
        for row in rows:
            settings_raw = row["settings_json"]
            try:
                settings = json.loads(settings_raw) if settings_raw else None
            except json.JSONDecodeError:
                settings = settings_raw

            tournaments.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "status": row["status"],
                    "date_start": row["date_start"],
                    "venue": row["venue"],
                    "settings_json": settings,
                }
            )
        return tournaments


async def get_team_members() -> dict[int, list[int]]:
    """Return a mapping of team_id -> list[user_id] if the table exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if not await _table_exists(db, "team_members"):
            return {}

        cur = await db.execute("SELECT team_id, user_id FROM team_members")
        rows = await cur.fetchall()

        members: dict[int, list[int]] = {}
        for row in rows:
            members.setdefault(row["team_id"], []).append(row["user_id"])
        return members


async def get_all_teams() -> list[dict]:
    """Return all teams from the newest structure if present, otherwise fall back."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if await _table_exists(db, "teams_new"):
            cur = await db.execute(
                "SELECT id, name, tournament_id, captain_user_id, status FROM teams_new"
            )
        elif await _table_exists(db, "teams"):
            cur = await db.execute(
                "SELECT id, team_name as name, NULL as tournament_id, NULL as captain_user_id, NULL as status FROM teams"
            )
        else:
            return []

        rows = await cur.fetchall()
        members = await get_team_members()

        teams: list[dict] = []
        for row in rows:
            team_dict = {
                "id": row["id"],
                "name": row["name"],
                "tournament_id": row["tournament_id"],
                "captain_user_id": row["captain_user_id"],
                "status": row["status"],
            }
            team_players = members.get(row["id"])
            if team_players is not None:
                team_dict["players"] = team_players
            teams.append(team_dict)

        return teams


async def get_all_matches() -> list[dict]:
    """Return all matches from the matches table if present."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if not await _table_exists(db, "matches"):
            return []

        cur = await db.execute(
            """
            SELECT id, tournament_id, stage, group_name, round, court, start_at,
                   team_home_id, team_away_id, score_home, score_away, status
            FROM matches
            """
        )
        rows = await cur.fetchall()
        return [dict(row) for row in rows]


async def get_last_team_for_user(user_id: int) -> Optional[dict]:
    """Return the most recent team membership for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if await _table_exists(db, "team_members"):
            cur = await db.execute(
                "SELECT team_id, tournament_id FROM team_members WHERE user_id = ? ORDER BY rowid DESC LIMIT 1",
                (user_id,),
            )
            row = await cur.fetchone()
            if row:
                return {"team_id": row["team_id"], "tournament_id": row["tournament_id"]}

        if await _table_exists(db, "teams_new"):
            cur = await db.execute(
                "SELECT id as team_id, tournament_id FROM teams_new WHERE captain_user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            row = await cur.fetchone()
            if row:
                return {"team_id": row["team_id"], "tournament_id": row["tournament_id"]}

        return None


async def get_team_by_id(team_id: int) -> Optional[dict]:
    """Return a team by id from the available team table."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if await _table_exists(db, "teams_new"):
            cur = await db.execute(
                "SELECT id, name, tournament_id FROM teams_new WHERE id = ?", (team_id,)
            )
        elif await _table_exists(db, "teams"):
            cur = await db.execute(
                "SELECT id, team_name as name, NULL as tournament_id FROM teams WHERE id = ?",
                (team_id,),
            )
        else:
            return None

        row = await cur.fetchone()
        return dict(row) if row else None


async def get_teams_for_tournament(tournament_id: int) -> list[dict]:
    """Return teams belonging to a specific tournament."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if await _table_exists(db, "teams_new"):
            cur = await db.execute(
                "SELECT id, name, tournament_id, captain_user_id, status FROM teams_new WHERE tournament_id = ?",
                (tournament_id,),
            )
        else:
            return []

        rows = await cur.fetchall()
        members = await get_team_members()

        teams: list[dict] = []
        for row in rows:
            team_dict = {
                "id": row["id"],
                "name": row["name"],
                "tournament_id": row["tournament_id"],
                "captain_user_id": row["captain_user_id"],
                "status": row["status"],
            }
            team_players = members.get(row["id"])
            if team_players is not None:
                team_dict["players"] = team_players
            teams.append(team_dict)

        return teams
