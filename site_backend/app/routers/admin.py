import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.db import get_conn
from app.deps import require_admin
from app.http import ok, page_meta

router = APIRouter()


class TournamentCreateIn(BaseModel):
    name: str
    status: str = 'draft'
    date_start: str | None = None
    venue: str | None = None


class TournamentPatchIn(BaseModel):
    name: str | None = None
    date_start: str | None = None
    venue: str | None = None


class TournamentStatusIn(BaseModel):
    status: str


class MatchCreateIn(BaseModel):
    stage: str | None = None
    team_home_name: str
    team_away_name: str


class MatchPatchIn(BaseModel):
    stage: str | None = None
    score_home: int | None = None
    score_away: int | None = None
    status: str | None = None


class PollCreateIn(BaseModel):
    question: str
    options: list[str]
    tournament_id: int | None = None


class SuggestionReplyIn(BaseModel):
    reply_text: str


class AchievementGrantIn(BaseModel):
    tournament_id: int = 0
    user_id: int
    achievement_code: str
    note: str | None = None


@router.post('/tournaments')
def create_tournament(payload: TournamentCreateIn, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            'INSERT INTO tournaments(name, status, date_start, venue) VALUES (%s, %s, %s, %s) RETURNING id',
            (payload.name, payload.status, payload.date_start, payload.venue),
        )
        tid = cur.fetchone()['id']
        conn.commit()
    return ok({'tournament_id': tid})


@router.patch('/tournaments/{tournament_id}')
def update_tournament(tournament_id: int, payload: TournamentPatchIn, _=Depends(require_admin)) -> dict:
    updates = []
    params: list = []
    if payload.name is not None:
        updates.append('name=%s')
        params.append(payload.name)
    if payload.date_start is not None:
        updates.append('date_start=%s')
        params.append(payload.date_start)
    if payload.venue is not None:
        updates.append('venue=%s')
        params.append(payload.venue)

    if not updates:
        return ok({'updated': 0})

    params.append(tournament_id)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE tournaments SET {', '.join(updates)} WHERE id=%s", tuple(params))
        updated = cur.rowcount
        conn.commit()

    if updated == 0:
        raise HTTPException(status_code=404, detail='Tournament not found')
    return ok({'updated': updated})


@router.post('/tournaments/{tournament_id}/status')
def change_tournament_status(tournament_id: int, payload: TournamentStatusIn, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('UPDATE tournaments SET status=%s WHERE id=%s', (payload.status, tournament_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Tournament not found')
        conn.commit()
    return ok({'status': payload.status})


@router.post('/tournaments/{tournament_id}/matches')
def create_match(tournament_id: int, payload: MatchCreateIn, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO matches_simple (tournament_id, stage, team_home_name, team_away_name, status)
            VALUES (%s, %s, %s, %s, 'scheduled')
            RETURNING id
            """,
            (tournament_id, payload.stage, payload.team_home_name, payload.team_away_name),
        )
        mid = cur.fetchone()['id']
        conn.commit()
    return ok({'match_id': mid})


@router.patch('/matches/{match_id}')
def update_match(match_id: int, payload: MatchPatchIn, _=Depends(require_admin)) -> dict:
    updates = []
    params: list = []
    if payload.stage is not None:
        updates.append('stage=%s')
        params.append(payload.stage)
    if payload.score_home is not None:
        updates.append('score_home=%s')
        params.append(payload.score_home)
    if payload.score_away is not None:
        updates.append('score_away=%s')
        params.append(payload.score_away)
    if payload.status is not None:
        updates.append('status=%s')
        params.append(payload.status)

    if not updates:
        return ok({'updated': 0})

    params.append(match_id)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE matches_simple SET {', '.join(updates)} WHERE id=%s", tuple(params))
        updated = cur.rowcount
        conn.commit()

    if updated == 0:
        raise HTTPException(status_code=404, detail='Match not found')
    return ok({'updated': updated})


@router.delete('/matches/{match_id}')
def delete_match(match_id: int, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM matches_simple WHERE id=%s', (match_id,))
        deleted = cur.rowcount
        conn.commit()

    if deleted == 0:
        raise HTTPException(status_code=404, detail='Match not found')
    return ok({'deleted': deleted})


@router.post('/polls')
def create_poll(payload: PollCreateIn, _=Depends(require_admin)) -> dict:
    if len(payload.options) < 2:
        raise HTTPException(status_code=400, detail='At least 2 options are required')

    group_id = str(uuid.uuid4())
    options_json = json.dumps(payload.options, ensure_ascii=False)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            'INSERT INTO polls_group (group_id, question, options, tournament_id) VALUES (%s, %s, %s, %s)',
            (group_id, payload.question, options_json, payload.tournament_id),
        )
        conn.commit()

    return ok({'group_id': group_id})


@router.post('/polls/{group_id}/close')
def close_poll(group_id: str, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('UPDATE polls_group SET is_closed=1 WHERE group_id=%s', (group_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Poll group not found')
        conn.commit()
    return ok({'group_id': group_id, 'is_closed': 1})


@router.get('/polls/{group_id}/results')
def poll_results(group_id: str, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT question, options FROM polls_group WHERE group_id=%s', (group_id,))
        pg = cur.fetchone()
        if not pg:
            raise HTTPException(status_code=404, detail='Poll group not found')

        options = json.loads(pg['options']) if isinstance(pg['options'], str) else pg['options']

        cur.execute('SELECT poll_id FROM polls WHERE group_id=%s', (group_id,))
        poll_ids = [r['poll_id'] for r in cur.fetchall()]

        if not poll_ids:
            return ok({'group_id': group_id, 'question': pg['question'], 'options': options, 'votes': []})

        cur.execute(
            'SELECT option_id, COUNT(*) AS votes FROM poll_votes WHERE poll_id = ANY(%s) GROUP BY option_id ORDER BY option_id',
            (poll_ids,),
        )
        votes = cur.fetchall()

    return ok({'group_id': group_id, 'question': pg['question'], 'options': options, 'votes': votes})


@router.get('/suggestions')
def list_suggestions(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _=Depends(require_admin),
) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            'SELECT id, user_id, text, status, created_at, tournament_id '
            'FROM suggestions ORDER BY created_at DESC LIMIT %s OFFSET %s',
            (limit, offset),
        )
        rows = cur.fetchall()
    return ok(rows, **page_meta(limit=limit, offset=offset))


@router.post('/suggestions/{suggestion_id}/reply')
def reply_suggestion(suggestion_id: int, payload: SuggestionReplyIn, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE suggestions SET status='answered', reply_text=%s, replied_at=NOW() WHERE id=%s",
            (payload.reply_text, suggestion_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Suggestion not found')
        conn.commit()

    return ok({'suggestion_id': suggestion_id, 'reply_text': payload.reply_text})


@router.post('/achievements/grant')
def grant_achievement(payload: AchievementGrantIn, _=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT id FROM achievements WHERE code=%s', (payload.achievement_code,))
        ach = cur.fetchone()
        if not ach:
            raise HTTPException(status_code=404, detail='Achievement code not found')

        cur.execute(
            """
            INSERT INTO player_achievements (tournament_id, user_id, achievement_id, note)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tournament_id, user_id, achievement_id) DO NOTHING
            """,
            (payload.tournament_id, payload.user_id, ach['id'], payload.note),
        )
        inserted = cur.rowcount
        conn.commit()

    return ok({'inserted': inserted})


@router.post('/achievements/backfill')
def backfill_achievements(_=Depends(require_admin)) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO player_achievements (tournament_id, user_id, achievement_id)
            SELECT 0, pa.user_id, pa.achievement_id
            FROM player_achievements pa
            WHERE pa.tournament_id <> 0
            ON CONFLICT (tournament_id, user_id, achievement_id) DO NOTHING
            """
        )
        inserted = cur.rowcount
        conn.commit()

    return ok({'inserted': inserted})
