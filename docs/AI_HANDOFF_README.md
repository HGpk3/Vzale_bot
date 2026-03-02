# AI Handoff README (Project State + Next Plan)

## 0) Latest Update (2026-03-02)
- Added production-grade JWT flow improvements:
  - refresh token purge function (`purge_refresh_tokens`)
  - startup purge on API boot
  - admin endpoint `POST /v1/auth/cleanup-refresh`
- Added runtime schema safety upgrades:
  - `suggestions.reply_text`, `suggestions.replied_at` columns auto-created if missing
  - index on `web_users(username)`
- Added CORS config and safer 500-error handling:
  - `CORS_ORIGINS` env
  - internal error text hidden outside `APP_ENV=dev`
- Added script to provision website credentials:
  - `site_backend/scripts/create_web_user.py`
- Added extra unit tests:
  - `site_backend/tests/test_deps.py`
  - `site_backend/tests/test_http.py`

## 1) Current Project State
Repository has 3 main parts:
- `VZALE_BOT/` - Telegram bot (legacy monolith, already adapted with DB compatibility layer)
- `site_backend/` - FastAPI backend for website/admin panel (real DB endpoints implemented)
- `site_web/` - frontend scaffold/docs only (implementation pending)

Database model:
- Single source of truth is PostgreSQL.
- Migration from SQLite completed successfully by user.

## 2) What Is Already Done
### Bot
- Canonical bot file selected: `VZALE_BOT/bot_with_broadcast_poll.py`.
- Added DB compatibility layer: `VZALE_BOT/app/db_compat.py`.
- Bot can use:
  - PostgreSQL when `DATABASE_URL` is set.
  - SQLite fallback when `DATABASE_URL` is missing.
- Critical duplicate handlers/conflicts cleaned.
- Entrypoint standardized: `python -m app.main`.

### Site Backend
- FastAPI app scaffold created.
- Implemented routers with DB-backed operations:
  - auth (`/v1/auth/*`)
  - me (`/v1/me/*`)
  - tournaments (`/v1/tournaments/*`)
  - teams (`/v1/teams/*`)
  - matches (`/v1/matches/*`)
  - admin (`/v1/admin/*`)
- Added admin/header dependency model:
  - protected endpoints use `X-User-Id`
  - admin endpoints validate `ADMIN_IDS`

### Infrastructure
- Dockerized stack:
  - `postgres`
  - `api`
  - `bot`
- `docker-compose.yml` added.
- `.env.example` added.
- Runbook updated: `docs/RUN_ALL.md`.

## 3) How To Run (Authoritative)
Use `docs/RUN_ALL.md` as source of truth.

Quick start:
1. `cp .env.example .env`
2. fill `BOT_TOKEN`
3. `docker compose up --build -d`
4. check API:
   - `/health`
   - `/docs`

## 4) API Status
### Implemented now (MVP-level)
- Tournaments read flow (list/detail/info/standings/matches)
- Team lifecycle (create/join/leave/remove member)
- Match detail/finish/stats upsert
- Admin CRUD-ish for tournaments/matches/polls/suggestions/achievements
- Basic auth/login/link placeholders with working DB checks

### Not production-hardened yet
- No strict JWT auth/refresh persistence yet (current token format is lightweight MVP)
- No rate limiting / anti-abuse / audit log yet
- No formal service/repository split yet
- No frontend app implementation yet

## 5) Immediate Next Plan (Recommended Order)
1. **Auth hardening**
   - replace MVP token approach with JWT + refresh table
   - add middleware for bearer auth
2. **API normalization**
   - unify response envelopes and error format
   - add pagination for heavy lists
3. **Service layer extraction**
   - move SQL out of routers into service/repository modules
4. **Frontend implementation (site_web)**
   - Next.js app bootstrap
   - screens: login, dashboard, tournaments, team, admin
5. **Observability + quality**
   - add tests (pytest), lint, type checks
   - add structured logs and request IDs

## 6) Frontend Build Plan (site_web)
Phase A:
- bootstrap Next.js + TS
- API client module
- auth guard + base layout

Phase B:
- user pages: profile/team/tournaments/matches/achievements/stats

Phase C:
- admin pages: tournaments/teams/matches/polls/suggestions

Phase D:
- public pages + live updates

## 7) Risks / Technical Debt
- Bot file is still monolithic and large; behavior changes can be risky without tests.
- Some SQL still tailored from SQLite history; compatibility layer handles much, but full native Postgres refactor is still needed.
- Admin auth currently trusts `X-User-Id`; acceptable for local/internal stage only.

## 8) Definition of Done (Near-term)
A near-term milestone is complete when:
- Docker stack starts with one command.
- Bot works in PostgreSQL mode.
- API key flows tested via Swagger/Postman.
- Minimal frontend can perform end-to-end user journey:
  - login -> join/create team -> open tournament -> view matches/stats.

## 9) Useful File Map
- Bot entrypoint: `VZALE_BOT/app/main.py`
- Bot core: `VZALE_BOT/bot_with_broadcast_poll.py`
- Bot DB compat: `VZALE_BOT/app/db_compat.py`
- API entrypoint: `site_backend/app/main.py`
- API routers: `site_backend/app/routers/*.py`
- Compose: `docker-compose.yml`
- Runbook: `docs/RUN_ALL.md`
- Backlog: `docs/SITE_BACKLOG.md`
- API draft: `docs/SITE_API_V1.md`

## 10) Notes for Next AI Session
When continuing work:
1. Start from `docs/RUN_ALL.md` and ensure stack is up.
2. Prioritize auth hardening and frontend bootstrap.
3. Keep backward compatibility for existing bot behavior.
4. Avoid destructive DB operations unless explicitly requested.
