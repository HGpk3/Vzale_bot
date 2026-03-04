import bcrypt
import jwt
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.config import settings
from app.db import get_conn, purge_refresh_tokens
from app.deps import CurrentUser, current_user, require_admin
from app.http import ok
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
    now_utc,
    parse_admin_ids,
)

router = APIRouter()


class TelegramLinkIn(BaseModel):
    telegram_id: int
    full_name: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str | None = None


class CleanupRefreshIn(BaseModel):
    retention_days: int | None = None


class BotLoginFinishIn(BaseModel):
    session_id: str


class BotLoginConfirmIn(BaseModel):
    session_id: str
    telegram_id: int
    full_name: str | None = None
    username: str | None = None


def _issue_tokens(cur, uid: int) -> dict:
    is_admin = uid in parse_admin_ids()
    access_token = create_access_token(user_id=uid, is_admin=is_admin)
    refresh_token, refresh_exp = create_refresh_token(user_id=uid)
    refresh_hash = hash_refresh_token(refresh_token)
    cur.execute(
        """
        INSERT INTO auth_refresh_tokens(token_hash, user_id, expires_at)
        VALUES (%s, %s, %s)
        """,
        (refresh_hash, uid, refresh_exp),
    )
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'bearer',
        'user_id': uid,
        'is_admin': is_admin,
    }


@router.post('/telegram/link')
def telegram_link(payload: TelegramLinkIn) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, full_name)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                full_name = COALESCE(EXCLUDED.full_name, users.full_name)
            RETURNING user_id, full_name
            """,
            (payload.telegram_id, payload.full_name),
        )
        row = cur.fetchone()
        conn.commit()
    return ok(row)


@router.post('/login')
def login(payload: LoginIn) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            'SELECT telegram_id, username, password_hash FROM web_users WHERE username=%s',
            (payload.username,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=401, detail='Invalid credentials')

        password_hash = row.get('password_hash')
        if not password_hash:
            raise HTTPException(status_code=401, detail='Invalid credentials')

        if not bcrypt.checkpw(payload.password.encode('utf-8'), password_hash.encode('utf-8')):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        uid = int(row['telegram_id'])
        token_payload = _issue_tokens(cur, uid)
        conn.commit()

    return ok(token_payload)


@router.post('/bot-login/start')
def bot_login_start() -> dict:
    session_id = uuid.uuid4().hex
    code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
    expires_at = now_utc() + timedelta(seconds=settings.bot_login_ttl_seconds)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth_login_sessions(session_id, one_time_code, status, expires_at)
            VALUES (%s, %s, 'pending', %s)
            """,
            (session_id, code, expires_at),
        )
        conn.commit()

    return ok(
        {
            'session_id': session_id,
            'code': code,
            'expires_at': expires_at.isoformat(),
            'expires_in_seconds': settings.bot_login_ttl_seconds,
        }
    )


@router.get('/bot-login/status/{session_id}')
def bot_login_status(session_id: str) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT session_id, status, telegram_id, full_name, username, approved_at, consumed_at, expires_at
            FROM auth_login_sessions
            WHERE session_id=%s
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Login session not found')

        if row['status'] == 'pending' and row['expires_at'] <= now_utc():
            cur.execute("UPDATE auth_login_sessions SET status='expired' WHERE session_id=%s", (session_id,))
            conn.commit()
            row['status'] = 'expired'

    status = str(row['status'])
    return ok(
        {
            'session_id': session_id,
            'status': status,
            'approved': status in ('approved', 'consumed'),
            'expired': status == 'expired',
            'consumed': status == 'consumed',
            'telegram_id': row.get('telegram_id'),
            'full_name': row.get('full_name'),
            'username': row.get('username'),
            'approved_at': row.get('approved_at').isoformat() if row.get('approved_at') else None,
            'expires_at': row.get('expires_at').isoformat() if row.get('expires_at') else None,
        }
    )


@router.post('/bot-login/finish')
def bot_login_finish(payload: BotLoginFinishIn) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT session_id, status, telegram_id, expires_at, consumed_at
            FROM auth_login_sessions
            WHERE session_id=%s
            """,
            (payload.session_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Login session not found')

        if row['expires_at'] <= now_utc():
            cur.execute("UPDATE auth_login_sessions SET status='expired' WHERE session_id=%s", (payload.session_id,))
            conn.commit()
            raise HTTPException(status_code=400, detail='Login session expired')

        if row['status'] != 'approved':
            raise HTTPException(status_code=409, detail='Login session is not approved yet')

        if row['consumed_at'] is not None:
            raise HTTPException(status_code=409, detail='Login session already consumed')

        uid = int(row['telegram_id']) if row['telegram_id'] is not None else None
        if uid is None:
            raise HTTPException(status_code=400, detail='Login session has no telegram user')

        token_payload = _issue_tokens(cur, uid)
        cur.execute(
            """
            UPDATE auth_login_sessions
            SET status='consumed', consumed_at=NOW()
            WHERE session_id=%s
            """,
            (payload.session_id,),
        )
        conn.commit()

    return ok(token_payload)


@router.post('/bot-login/confirm')
def bot_login_confirm(
    payload: BotLoginConfirmIn,
    x_bot_login_secret: str | None = Header(default=None, alias='X-Bot-Login-Secret'),
) -> dict:
    if x_bot_login_secret != settings.bot_login_secret:
        raise HTTPException(status_code=401, detail='Invalid bot login secret')

    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT session_id, status, expires_at, consumed_at
            FROM auth_login_sessions
            WHERE session_id=%s
            """,
            (payload.session_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Login session not found')

        if row['consumed_at'] is not None or row['status'] == 'consumed':
            raise HTTPException(status_code=409, detail='Login session already consumed')

        if row['expires_at'] <= now_utc():
            cur.execute("UPDATE auth_login_sessions SET status='expired' WHERE session_id=%s", (payload.session_id,))
            conn.commit()
            raise HTTPException(status_code=400, detail='Login session expired')

        cur.execute(
            """
            INSERT INTO users (user_id, full_name)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                full_name = COALESCE(EXCLUDED.full_name, users.full_name)
            """,
            (payload.telegram_id, payload.full_name),
        )

        cur.execute(
            """
            UPDATE auth_login_sessions
            SET status='approved',
                approved_at=NOW(),
                telegram_id=%s,
                full_name=COALESCE(%s, full_name),
                username=COALESCE(%s, username)
            WHERE session_id=%s
            """,
            (payload.telegram_id, payload.full_name, payload.username, payload.session_id),
        )
        conn.commit()

    return ok({'approved': True, 'session_id': payload.session_id, 'telegram_id': payload.telegram_id})


@router.post('/refresh')
def refresh(payload: RefreshIn) -> dict:
    try:
        decoded = decode_token(payload.refresh_token, expected_type='refresh')
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail='Invalid refresh token') from exc

    sub = decoded.get('sub')
    if not sub or not str(sub).isdigit():
        raise HTTPException(status_code=401, detail='Invalid refresh subject')

    uid = int(sub)
    is_admin = uid in parse_admin_ids()

    old_hash = hash_refresh_token(payload.refresh_token)
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT token_hash, revoked_at, expires_at
            FROM auth_refresh_tokens
            WHERE token_hash=%s AND user_id=%s
            """,
            (old_hash, uid),
        )
        stored = cur.fetchone()

        if not stored:
            raise HTTPException(status_code=401, detail='Refresh token not found')
        if stored['revoked_at'] is not None:
            raise HTTPException(status_code=401, detail='Refresh token revoked')
        if stored['expires_at'] <= now_utc():
            raise HTTPException(status_code=401, detail='Refresh token expired')

        new_refresh, new_exp = create_refresh_token(user_id=uid)
        new_hash = hash_refresh_token(new_refresh)

        cur.execute(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at=NOW(), replaced_by_hash=%s
            WHERE token_hash=%s
            """,
            (new_hash, old_hash),
        )

        cur.execute(
            'INSERT INTO auth_refresh_tokens(token_hash, user_id, expires_at) VALUES (%s, %s, %s)',
            (new_hash, uid, new_exp),
        )
        conn.commit()

    access = create_access_token(user_id=uid, is_admin=is_admin)
    return ok({'access_token': access, 'refresh_token': new_refresh, 'token_type': 'bearer'})


@router.post('/logout')
def logout(payload: LogoutIn, user: CurrentUser = Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        if payload.refresh_token:
            token_hash = hash_refresh_token(payload.refresh_token)
            cur.execute(
                """
                UPDATE auth_refresh_tokens
                SET revoked_at=NOW()
                WHERE token_hash=%s AND user_id=%s AND revoked_at IS NULL
                """,
                (token_hash, user.user_id),
            )
        else:
            cur.execute(
                """
                UPDATE auth_refresh_tokens
                SET revoked_at=NOW()
                WHERE user_id=%s AND revoked_at IS NULL
                """,
                (user.user_id,),
            )
        conn.commit()

    return ok({'logged_out': True})


@router.post('/cleanup-refresh')
def cleanup_refresh_tokens(
    payload: CleanupRefreshIn | None = None,
    _admin: CurrentUser = Depends(require_admin),
) -> dict:
    retention_days = settings.refresh_token_retention_days
    if payload and payload.retention_days:
        retention_days = payload.retention_days
    if retention_days < 1 or retention_days > 365:
        raise HTTPException(status_code=400, detail='retention_days must be in range 1..365')

    deleted = purge_refresh_tokens(retention_days=retention_days)
    return ok({'deleted': deleted, 'retention_days': retention_days})
