# Site Backlog

## Epic A: Foundation
- A1: Create backend service skeleton (FastAPI)
- A2: Add environment/config loader and health endpoint
- A3: Add DB layer for PostgreSQL
- A4: Add migration workflow (Alembic)
- A5: Add CI checks (lint, tests, type checks)

## Epic B: Auth & Users
- B1: Telegram account linking endpoint
- B2: Session auth (access + refresh tokens)
- B3: User profile API (`GET/PATCH /me`)
- B4: Web credentials management (username/password hash)

## Epic C: Tournaments (Parity)
- C1: `GET /tournaments` with active/archive filters
- C2: `GET /tournaments/{id}` detail
- C3: `GET /tournaments/{id}/info` sections
- C4: `GET /tournaments/{id}/standings`
- C5: `GET /tournaments/{id}/matches` (scheduled/finished)

## Epic D: Teams (Parity)
- D1: `POST /teams` create team
- D2: `POST /teams/join` by invite code
- D3: `POST /teams/{id}/leave`
- D4: `DELETE /teams/{id}/members/{user_id}` (captain)
- D5: `POST /teams/{id}/invite-code/regenerate` (admin/captain)

## Epic E: Admin Operations
- E1: Tournament CRUD + status transitions
- E2: Team payment toggles
- E3: Match create/edit/delete
- E4: Match finish + score save
- E5: Poll create/close/results
- E6: Suggestion queue and admin replies

## Epic F: Achievements & Stats
- F1: Achievement catalog APIs
- F2: User achievement progress API
- F3: Manual grant/revoke APIs
- F4: Backfill operation endpoints
- F5: Rating and player stats APIs

## Epic G: Realtime + Public
- G1: Live match websocket channel
- G2: Public tournament page API
- G3: Public leaderboard API
- G4: Cache strategy for heavy reads

## Epic H: Web Frontend
- H1: App shell + auth guard
- H2: User cabinet (profile/team/achievements/stats)
- H3: Tournament pages
- H4: Admin panel
- H5: Public tournament portal

## Priority Order (Now)
1. A1-A4
2. B2-B3
3. C1-C5
4. D1-D4
5. E1-E4
