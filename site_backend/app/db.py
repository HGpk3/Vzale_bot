from contextlib import contextmanager

import psycopg
from fastapi import HTTPException

from app.config import settings


@contextmanager
def get_conn():
    if not settings.database_url:
        raise HTTPException(status_code=500, detail='DATABASE_URL is not configured')
    conn = psycopg.connect(settings.database_url)
    try:
        yield conn
    finally:
        conn.close()


def init_runtime_schema() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ,
                replaced_by_hash TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_user_id ON auth_refresh_tokens(user_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_expires_at ON auth_refresh_tokens(expires_at)"
        )
        cur.execute(
            "ALTER TABLE IF EXISTS suggestions ADD COLUMN IF NOT EXISTS reply_text TEXT"
        )
        cur.execute(
            "ALTER TABLE IF EXISTS suggestions ADD COLUMN IF NOT EXISTS replied_at TIMESTAMPTZ"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_users_username ON web_users(username)"
        )
        conn.commit()


def purge_refresh_tokens(*, retention_days: int) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM auth_refresh_tokens
            WHERE expires_at < NOW()
               OR (
                    revoked_at IS NOT NULL
                    AND revoked_at < NOW() - (%s * INTERVAL '1 day')
               )
            """,
            (retention_days,),
        )
        deleted = cur.rowcount
        conn.commit()
    return deleted
