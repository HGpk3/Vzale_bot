from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.db import get_conn
from app.deps import current_user
from app.http import ok, page_meta

router = APIRouter()


class MeUpdateIn(BaseModel):
    full_name: str | None = None
    current_tournament_id: int | None = None


@router.get('')
def me(user=Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            'SELECT user_id, full_name, team, current_tournament_id FROM users WHERE user_id=%s',
            (user.user_id,),
        )
        row = cur.fetchone()

    if not row:
        row = {'user_id': user.user_id, 'full_name': None, 'team': None, 'current_tournament_id': None}
    return ok(row)


@router.patch('')
def me_update(payload: MeUpdateIn, user=Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, full_name, current_tournament_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                full_name = COALESCE(EXCLUDED.full_name, users.full_name),
                current_tournament_id = COALESCE(EXCLUDED.current_tournament_id, users.current_tournament_id)
            RETURNING user_id, full_name, team, current_tournament_id
            """,
            (user.user_id, payload.full_name, payload.current_tournament_id),
        )
        row = cur.fetchone()
        conn.commit()
    return ok(row)


@router.get('/teams')
def my_teams(user=Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT DISTINCT team_name FROM teams WHERE member_id=%s ORDER BY team_name', (user.user_id,))
        rows = cur.fetchall()
    return ok(rows)


@router.get('/achievements')
def my_achievements(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user=Depends(current_user),
) -> dict:
    q = (
        'SELECT pa.tournament_id, a.code, a.title, a.description, a.emoji, a.tier, pa.awarded_at '
        'FROM player_achievements pa '
        'JOIN achievements a ON a.id = pa.achievement_id '
        'WHERE pa.user_id=%s '
        'ORDER BY pa.tournament_id DESC, a.order_index ASC, a.title ASC '
        'LIMIT %s OFFSET %s'
    )
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(q, (user.user_id, limit, offset))
        rows = cur.fetchall()
    return ok(rows, **page_meta(limit=limit, offset=offset))


@router.get('/stats')
def my_stats(user=Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
              COALESCE(SUM(games), 0) as games,
              COALESCE(SUM(wins), 0) as wins,
              COALESCE(SUM(losses), 0) as losses,
              COALESCE(SUM(points), 0) as points,
              COALESCE(SUM(assists), 0) as assists,
              COALESCE(SUM(blocks), 0) as blocks
            FROM player_stats
            WHERE user_id=%s
            """,
            (user.user_id,),
        )
        agg = cur.fetchone() or {}

        cur.execute('SELECT rating, games FROM player_ratings WHERE user_id=%s', (user.user_id,))
        rating = cur.fetchone() or {'rating': 1000, 'games': 0}

    return ok({'aggregate': agg, 'rating_global': rating})
