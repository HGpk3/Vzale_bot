#!/usr/bin/env python3
import argparse
import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql

TABLE_ORDER = [
    "tournaments",
    "users",
    "teams",
    "team_security",
    "free_agents",
    "teams_new",
    "team_members",
    "free_agents_new",
    "team_security_new",
    "tournament_info",
    "matches",
    "standings",
    "polls_group",
    "polls",
    "poll_votes",
    "suggestions",
    "tournament_team_names",
    "matches_simple",
    "player_payments",
    "achievements",
    "team_achievements",
    "tournament_roster",
    "player_achievements",
    "player_match_stats",
    "player_stats",
    "player_ratings",
    "player_ratings_by_tournament",
    "web_users",
]


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Migrate VZALE SQLite DB to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default=str(root / "tournament.db"),
        help="Path to SQLite DB file",
    )
    parser.add_argument(
        "--schema-path",
        default=str(root / "sql" / "postgres_schema.sql"),
        help="Path to PostgreSQL schema SQL",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL connection URL (or set DATABASE_URL)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate all known tables before loading data",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Apply schema only, do not copy data",
    )
    return parser.parse_args()


def sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def apply_schema(pg_conn: psycopg.Connection, schema_path: str) -> None:
    schema_sql = Path(schema_path).read_text(encoding="utf-8")
    with pg_conn.cursor() as cur:
        cur.execute(schema_sql)
    pg_conn.commit()


def truncate_tables(pg_conn: psycopg.Connection, tables: list[str]) -> None:
    with pg_conn.cursor() as cur:
        stmt = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(sql.Identifier(t) for t in tables)
        )
        cur.execute(stmt)
    pg_conn.commit()


def copy_table(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection, table: str, batch_size: int = 1000) -> int:
    cols = table_columns(sqlite_conn, table)
    if not cols:
        return 0

    select_stmt = f"SELECT {', '.join(cols)} FROM {table}"
    insert_stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in cols),
        sql.SQL(", ").join(sql.Placeholder() for _ in cols),
    )

    inserted = 0
    src_cur = sqlite_conn.cursor()
    src_cur.execute(select_stmt)

    with pg_conn.cursor() as dst_cur:
        while True:
            rows = src_cur.fetchmany(batch_size)
            if not rows:
                break
            dst_cur.executemany(insert_stmt, rows)
            inserted += len(rows)

    pg_conn.commit()
    return inserted


def sync_sequences(pg_conn: psycopg.Connection, tables: list[str]) -> None:
    with pg_conn.cursor() as cur:
        for table in tables:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name=%s
                  AND column_default LIKE 'nextval(%%'
                """,
                (table,),
            )
            serial_cols = [r[0] for r in cur.fetchall()]
            for col in serial_cols:
                cur.execute("SELECT pg_get_serial_sequence(%s, %s)", (table, col))
                seq_row = cur.fetchone()
                if not seq_row or not seq_row[0]:
                    continue
                seq_name = seq_row[0]

                cur.execute(
                    sql.SQL("SELECT COALESCE(MAX({}), 0) FROM {}").format(
                        sql.Identifier(col),
                        sql.Identifier(table),
                    )
                )
                max_id = int(cur.fetchone()[0] or 0)

                if max_id > 0:
                    cur.execute("SELECT setval(%s, %s, true)", (seq_name, max_id))
                else:
                    cur.execute("SELECT setval(%s, 1, false)", (seq_name,))

    pg_conn.commit()


def main() -> int:
    args = parse_args()
    if not args.postgres_url:
        raise SystemExit("ERROR: Provide --postgres-url or set DATABASE_URL")

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        raise SystemExit(f"ERROR: SQLite DB not found: {sqlite_path}")

    with sqlite3.connect(str(sqlite_path)) as sconn, psycopg.connect(args.postgres_url) as pconn:
        pconn.autocommit = False

        print(f"Applying schema: {args.schema_path}")
        apply_schema(pconn, args.schema_path)

        if args.schema_only:
            print("Schema applied. Data copy skipped (--schema-only).")
            return 0

        src_tables = sqlite_tables(sconn)
        tables_to_copy = [t for t in TABLE_ORDER if t in src_tables]

        if args.truncate:
            print("Truncating target tables...")
            truncate_tables(pconn, tables_to_copy)

        print("Copying data...")
        for table in tables_to_copy:
            count = copy_table(sconn, pconn, table)
            print(f"  {table}: {count}")

        print("Syncing sequences...")
        sync_sequences(pconn, tables_to_copy)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
