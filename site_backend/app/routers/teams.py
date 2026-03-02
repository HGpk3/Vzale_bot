import random
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.config import settings
from app.db import get_conn
from app.deps import current_user
from app.http import ok

router = APIRouter()


def _gen_invite_code(n: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(random.choice(alphabet) for _ in range(n))


class TeamCreateIn(BaseModel):
    team_name: str
    tournament_id: int | None = None
    full_name: str | None = None


class TeamJoinByCodeIn(BaseModel):
    invite_code: str
    tournament_id: int | None = None
    full_name: str | None = None


class RegenerateInviteIn(BaseModel):
    pass


def _is_captain_or_admin(cur, actor_id: int, team_name: str) -> bool:
    admin_ids = {int(x.strip()) for x in settings.admin_ids.split(',') if x.strip().isdigit()}
    if actor_id in admin_ids:
        return True

    cur.execute(
        'SELECT 1 FROM tournament_roster WHERE team_name=%s AND user_id=%s AND is_captain=1 LIMIT 1',
        (team_name, actor_id),
    )
    if cur.fetchone():
        return True

    cur.execute('SELECT member_id FROM teams WHERE team_name=%s ORDER BY id ASC LIMIT 1', (team_name,))
    row = cur.fetchone()
    return bool(row and int(row['member_id']) == actor_id)


@router.post('')
def create_team(payload: TeamCreateIn, user=Depends(current_user)) -> dict:
    team_name = payload.team_name.strip()
    if not team_name:
        raise HTTPException(status_code=400, detail='team_name is required')

    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT 1 FROM teams WHERE team_name=%s AND member_id=%s LIMIT 1', (team_name, user.user_id))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail='User already in this team')

        cur.execute(
            """
            INSERT INTO users (user_id, full_name, team)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                full_name = COALESCE(EXCLUDED.full_name, users.full_name),
                team = EXCLUDED.team
            """,
            (user.user_id, payload.full_name or f'User {user.user_id}', team_name),
        )

        cur.execute(
            'INSERT INTO teams (team_name, member_id, member_name) VALUES (%s, %s, %s)',
            (team_name, user.user_id, payload.full_name or f'User {user.user_id}'),
        )

        if payload.tournament_id is not None:
            cur.execute(
                """
                INSERT INTO tournament_roster (tournament_id, team_name, user_id, full_name, is_captain)
                VALUES (%s, %s, %s, %s, 1)
                ON CONFLICT (tournament_id, team_name, user_id) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    is_captain = 1
                """,
                (payload.tournament_id, team_name, user.user_id, payload.full_name or f'User {user.user_id}'),
            )

        invite_code = _gen_invite_code(6)
        for _ in range(10):
            try:
                cur.execute(
                    """
                    INSERT INTO team_security (team_name, invite_code)
                    VALUES (%s, %s)
                    ON CONFLICT (team_name) DO UPDATE SET invite_code = EXCLUDED.invite_code
                    """,
                    (team_name, invite_code),
                )
                break
            except Exception:
                invite_code = _gen_invite_code(6)

        conn.commit()

    return ok({'team_name': team_name, 'invite_code': invite_code})


@router.post('/join-by-code')
def join_by_code(payload: TeamJoinByCodeIn, user=Depends(current_user)) -> dict:
    code = payload.invite_code.strip().upper()
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT team_name FROM team_security WHERE invite_code=%s', (code,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Invite code not found')

        team_name = row['team_name']

        cur.execute('SELECT 1 FROM teams WHERE team_name=%s AND member_id=%s LIMIT 1', (team_name, user.user_id))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail='Already in this team')

        cur.execute(
            """
            INSERT INTO users (user_id, full_name, team)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                full_name = COALESCE(EXCLUDED.full_name, users.full_name),
                team = EXCLUDED.team
            """,
            (user.user_id, payload.full_name or f'User {user.user_id}', team_name),
        )

        cur.execute(
            'INSERT INTO teams (team_name, member_id, member_name) VALUES (%s, %s, %s)',
            (team_name, user.user_id, payload.full_name or f'User {user.user_id}'),
        )

        if payload.tournament_id is not None:
            cur.execute(
                """
                INSERT INTO tournament_roster (tournament_id, team_name, user_id, full_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tournament_id, team_name, user_id) DO UPDATE SET
                    full_name = EXCLUDED.full_name
                """,
                (payload.tournament_id, team_name, user.user_id, payload.full_name or f'User {user.user_id}'),
            )

        conn.commit()

    return ok({'team_name': team_name})


@router.post('/{team_name}/leave')
def leave_team(team_name: str, user=Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('DELETE FROM teams WHERE team_name=%s AND member_id=%s', (team_name, user.user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='User not in team')

        cur.execute('UPDATE users SET team=NULL WHERE user_id=%s AND team=%s', (user.user_id, team_name))
        cur.execute('DELETE FROM tournament_roster WHERE team_name=%s AND user_id=%s', (team_name, user.user_id))
        conn.commit()

    return ok({'left': True})


@router.get('/{team_name}')
def team_detail(team_name: str, user=Depends(current_user)) -> dict:
    _ = user
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT member_id, member_name FROM teams WHERE team_name=%s ORDER BY member_name', (team_name,))
        members = cur.fetchall()

        cur.execute('SELECT invite_code FROM team_security WHERE team_name=%s', (team_name,))
        code_row = cur.fetchone()

    return ok({'team_name': team_name, 'invite_code': code_row['invite_code'] if code_row else None, 'members': members})


@router.delete('/{team_name}/members/{remove_user_id}')
def remove_member(team_name: str, remove_user_id: int, user=Depends(current_user)) -> dict:
    if remove_user_id == user.user_id:
        raise HTTPException(status_code=400, detail='Cannot remove self')

    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        if not _is_captain_or_admin(cur, user.user_id, team_name):
            raise HTTPException(status_code=403, detail='Only captain can remove members')

        cur.execute('DELETE FROM teams WHERE team_name=%s AND member_id=%s', (team_name, remove_user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Member not found in team')

        cur.execute('UPDATE users SET team=NULL WHERE user_id=%s AND team=%s', (remove_user_id, team_name))
        cur.execute('DELETE FROM tournament_roster WHERE team_name=%s AND user_id=%s', (team_name, remove_user_id))
        conn.commit()

    return ok({'removed_user_id': remove_user_id})


@router.post('/{team_name}/invite-code/regenerate')
def regenerate_invite(team_name: str, _: RegenerateInviteIn, user=Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        if not _is_captain_or_admin(cur, user.user_id, team_name):
            raise HTTPException(status_code=403, detail='Only captain can regenerate invite code')

        code = _gen_invite_code(6)
        for _ in range(12):
            try:
                cur.execute(
                    """
                    INSERT INTO team_security(team_name, invite_code)
                    VALUES (%s, %s)
                    ON CONFLICT (team_name) DO UPDATE SET invite_code=EXCLUDED.invite_code
                    """,
                    (team_name, code),
                )
                conn.commit()
                return ok({'team_name': team_name, 'invite_code': code})
            except Exception:
                code = _gen_invite_code(6)

    raise HTTPException(status_code=500, detail='Could not regenerate invite code')
