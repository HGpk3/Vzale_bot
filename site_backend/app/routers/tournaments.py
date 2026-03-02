from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from app.db import get_conn
from app.http import ok, page_meta

router = APIRouter()


@router.get('')
def list_tournaments(
    status: str = Query(default='active'),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
):
    active_statuses = ('announced', 'registration_open', 'running')

    if status == 'active':
        q = (
            'SELECT id, name, date_start, venue, COALESCE(status, \'draft\') AS status '
            'FROM tournaments WHERE COALESCE(status, \'draft\') = ANY(%s) '
            'ORDER BY id DESC LIMIT %s OFFSET %s'
        )
        params = (list(active_statuses), limit, offset)
    elif status == 'archived':
        q = (
            'SELECT id, name, date_start, venue, COALESCE(status, \'draft\') AS status '
            'FROM tournaments WHERE COALESCE(status, \'draft\') = %s '
            'ORDER BY id DESC LIMIT %s OFFSET %s'
        )
        params = ('archived', limit, offset)
    else:
        q = (
            'SELECT id, name, date_start, venue, COALESCE(status, \'draft\') AS status '
            'FROM tournaments ORDER BY id DESC LIMIT %s OFFSET %s'
        )
        params = (limit, offset)

    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(q, params)
        rows = cur.fetchall()
    return ok(rows, **page_meta(limit=limit, offset=offset))


@router.get('/{tournament_id}')
def get_tournament(tournament_id: int):
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            'SELECT id, name, date_start, venue, COALESCE(status, \'draft\') AS status '
            'FROM tournaments WHERE id=%s',
            (tournament_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail='Tournament not found')
    return ok(row)


@router.get('/{tournament_id}/info')
def tournament_info(tournament_id: int):
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            'SELECT section, content, updated_at '
            'FROM tournament_info WHERE tournament_id=%s ORDER BY section ASC',
            (tournament_id,),
        )
        rows = cur.fetchall()
    return ok(rows)


@router.get('/{tournament_id}/standings')
def standings(tournament_id: int):
    q = (
        'SELECT team, games, wins, losses, pf, pa FROM ('
        '  SELECT team_home_name AS team FROM matches_simple WHERE tournament_id=%s AND status=\'finished\''
        '  UNION '
        '  SELECT team_away_name AS team FROM matches_simple WHERE tournament_id=%s AND status=\'finished\''
        ') t '
        'LEFT JOIN LATERAL ('
        '  SELECT '
        '    COUNT(*) AS games, '
        '    SUM(CASE WHEN (m.team_home_name=t.team AND m.score_home>m.score_away) OR (m.team_away_name=t.team AND m.score_away>m.score_home) THEN 1 ELSE 0 END) AS wins, '
        '    SUM(CASE WHEN (m.team_home_name=t.team AND m.score_home<m.score_away) OR (m.team_away_name=t.team AND m.score_away<m.score_home) THEN 1 ELSE 0 END) AS losses, '
        '    SUM(CASE WHEN m.team_home_name=t.team THEN COALESCE(m.score_home,0) ELSE COALESCE(m.score_away,0) END) AS pf, '
        '    SUM(CASE WHEN m.team_home_name=t.team THEN COALESCE(m.score_away,0) ELSE COALESCE(m.score_home,0) END) AS pa '
        '  FROM matches_simple m '
        '  WHERE m.tournament_id=%s AND m.status=\'finished\' AND (m.team_home_name=t.team OR m.team_away_name=t.team)'
        ') s ON TRUE '
        'ORDER BY wins DESC, (COALESCE(pf,0)-COALESCE(pa,0)) DESC, COALESCE(pf,0) DESC, team ASC'
    )

    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(q, (tournament_id, tournament_id, tournament_id))
        rows = cur.fetchall()

    out = []
    for r in rows:
        pf = int(r.get('pf') or 0)
        pa = int(r.get('pa') or 0)
        out.append(
            {
                'team_name': r.get('team'),
                'games': int(r.get('games') or 0),
                'wins': int(r.get('wins') or 0),
                'losses': int(r.get('losses') or 0),
                'points_for': pf,
                'points_against': pa,
                'diff': pf - pa,
            }
        )

    return ok(out)


@router.get('/{tournament_id}/matches')
def matches(
    tournament_id: int,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = (
        'SELECT id, stage, team_home_name, team_away_name, score_home, score_away, '
        'COALESCE(status, \'scheduled\') AS status '
        'FROM matches_simple WHERE tournament_id=%s'
    )
    params: list = [tournament_id]

    if status:
        q += ' AND COALESCE(status, \'scheduled\')=%s'
        params.append(status)

    q += ' ORDER BY id DESC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()
    return ok(rows, **page_meta(limit=limit, offset=offset))
