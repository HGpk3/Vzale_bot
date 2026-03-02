# Site API v1 (Draft)

## Auth
- `POST /v1/auth/telegram/link`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`

## Me
- `GET /v1/me`
- `PATCH /v1/me`
- `GET /v1/me/teams`
- `GET /v1/me/achievements`
- `GET /v1/me/stats`

## Tournaments
- `GET /v1/tournaments?status=active|archived`
- `GET /v1/tournaments/{tournament_id}`
- `GET /v1/tournaments/{tournament_id}/info`
- `GET /v1/tournaments/{tournament_id}/standings`
- `GET /v1/tournaments/{tournament_id}/matches?status=scheduled|finished`

## Teams
- `POST /v1/teams`
- `POST /v1/teams/join-by-code`
- `POST /v1/teams/{team_name}/leave`
- `GET /v1/teams/{team_name}`
- `DELETE /v1/teams/{team_name}/members/{user_id}`

## Matches
- `GET /v1/matches/{match_id}`
- `POST /v1/matches/{match_id}/finish`
- `POST /v1/matches/{match_id}/stats`

## Admin
- `POST /v1/admin/tournaments`
- `PATCH /v1/admin/tournaments/{tournament_id}`
- `POST /v1/admin/tournaments/{tournament_id}/status`
- `POST /v1/admin/tournaments/{tournament_id}/matches`
- `PATCH /v1/admin/matches/{match_id}`
- `DELETE /v1/admin/matches/{match_id}`
- `POST /v1/admin/polls`
- `POST /v1/admin/polls/{group_id}/close`
- `GET /v1/admin/polls/{group_id}/results`
- `GET /v1/admin/suggestions`
- `POST /v1/admin/suggestions/{id}/reply`
- `POST /v1/admin/achievements/grant`
- `POST /v1/admin/achievements/backfill`

## Public
- `GET /v1/public/tournaments/{tournament_id}`
- `GET /v1/public/tournaments/{tournament_id}/leaderboard`
- `GET /v1/public/tournaments/{tournament_id}/schedule`
