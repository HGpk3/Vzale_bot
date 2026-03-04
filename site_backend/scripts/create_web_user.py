#!/usr/bin/env python3
import argparse
import os
import sys

import bcrypt
import psycopg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Create or update web_users credential record.')
    parser.add_argument('--telegram-id', type=int, required=True, help='Telegram numeric user ID')
    parser.add_argument('--username', required=True, help='Username for site login')
    parser.add_argument('--password', required=True, help='Plaintext password')
    parser.add_argument(
        '--database-url',
        default=os.getenv('DATABASE_URL', ''),
        help='Postgres DSN. Defaults to DATABASE_URL env var.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        print('DATABASE_URL is required (env or --database-url)', file=sys.stderr)
        return 1

    pwd_hash = bcrypt.hashpw(args.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    username = args.username.strip()
    if not username:
        print('username cannot be empty', file=sys.stderr)
        return 1

    with psycopg.connect(args.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL UNIQUE,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            INSERT INTO web_users (telegram_id, username, password_hash)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                password_hash = EXCLUDED.password_hash
            """,
            (args.telegram_id, username, pwd_hash),
        )
        conn.commit()

    print(f'web_user saved: telegram_id={args.telegram_id} username={username}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
