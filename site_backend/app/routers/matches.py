from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.db import get_conn
from app.deps import current_user, require_admin
from app.http import ok

router = APIRouter()


class MatchStatsIn(BaseModel):
    user_id: int
    team_name: str
    points: int = 0
    threes: int = 0
    assists: int = 0
    rebounds: int = 0
    steals: int = 0
    blocks: int = 0
    fouls: int = 0
    turnovers: int = 0
    minutes: int = 0


@router.get('/{match_id}')
def match_detail(match_id: int, _=Depends(current_user)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, tournament_id, stage, team_home_name, team_away_name,
                   score_home, score_away, COALESCE(status,'scheduled') AS status
            FROM matches_simple
            WHERE id=%s
            """,
            (match_id,),
        )
        match = cur.fetchone()

        if not match:
            raise HTTPException(status_code=404, detail='Match not found')

        cur.execute(
            """
            SELECT user_id, team_name, points, assists, blocks, rebounds, steals, fouls, turnovers, minutes
            FROM player_match_stats
            WHERE tournament_id=%s AND match_id=%s
            ORDER BY team_name, user_id
            """,
            (match['tournament_id'], match_id),
        )
        stats = cur.fetchall()

    return ok({'match': match, 'player_stats': stats})


@router.post('/{match_id}/finish')
def finish_match(match_id: int, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("UPDATE matches_simple SET status='finished' WHERE id=%s", (match_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Match not found')
        conn.commit()
    return ok({'match_id': match_id, 'status': 'finished'})


@router.post('/{match_id}/stats')
def match_stats(match_id: int, payload: MatchStatsIn, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT tournament_id FROM matches_simple WHERE id=%s', (match_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Match not found')
        tid = row['tournament_id']

        cur.execute(
            """
            INSERT INTO player_match_stats(
                tournament_id, match_id, team_name, user_id,
                points, threes, assists, rebounds, steals, blocks, fouls, turnovers, minutes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tournament_id, match_id, user_id) DO UPDATE SET
                team_name = EXCLUDED.team_name,
                points = EXCLUDED.points,
                threes = EXCLUDED.threes,
                assists = EXCLUDED.assists,
                rebounds = EXCLUDED.rebounds,
                steals = EXCLUDED.steals,
                blocks = EXCLUDED.blocks,
                fouls = EXCLUDED.fouls,
                turnovers = EXCLUDED.turnovers,
                minutes = EXCLUDED.minutes
            """,
            (
                tid,
                match_id,
                payload.team_name,
                payload.user_id,
                payload.points,
                payload.threes,
                payload.assists,
                payload.rebounds,
                payload.steals,
                payload.blocks,
                payload.fouls,
                payload.turnovers,
                payload.minutes,
            ),
        )
        conn.commit()

    return ok({'match_id': match_id, 'user_id': payload.user_id})
