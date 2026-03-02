# Bot Cleanup And Joint Hosting Plan

## What Is Broken Right Now
- `VZALE_BOT/Procfile` and `VZALE_BOT/start.sh` referenced a missing file: `bot_admin_aiogram3.py`.
- Canonical bot file: `VZALE_BOT/bot_with_broadcast_poll.py`.
- SQLite files are committed (`*.db`, `*.db-wal`, `*.db-shm`) and this causes state drift between environments.
- One large bot file contains duplicate handlers/functions with identical names and callback filters.

## Cleanup Strategy (Safe Order)
1. Canonical file is already selected: `VZALE_BOT/bot_with_broadcast_poll.py`.
2. Move repeated helper functions to small modules:
   - `db.py` (connection + repositories)
   - `keyboards.py`
   - `handlers/user.py`
   - `handlers/admin.py`
3. Remove duplicate handler registrations (same callback filter defined more than once).
4. Keep one source of truth for tournament/payment constants in `config.py`.
5. Add smoke checks:
   - import check (`python -m py_compile`)
   - bot startup check in test environment
6. Only after step 1-5, delete/archive the second duplicate bot file.

## Hosting Architecture For Site + Bot (No Conflict)
Use shared PostgreSQL instead of SQLite.

- Site:
  - Can stay on Vercel (frontend + optional API routes).
- Bot:
  - Run as worker on Render/Railway/Fly.io (long-running polling or webhook process).
- Data:
  - Managed Postgres (Neon/Supabase/Render Postgres).
- Optional:
  - Redis for FSM/session/cache/rate-limit.

## Why This Solves “Parallel Hosting” Problems
- SQLite file locks and local file state do not work reliably across two hosts.
- Postgres is designed for concurrent reads/writes from multiple services.
- Both site and bot read/write the same central DB, so no split state.

## Minimal Migration Path
1. Create Postgres schema equivalent to current SQLite tables.
2. Export SQLite data and import into Postgres.
3. Replace direct `sqlite3/aiosqlite` calls with a DB layer (or SQLAlchemy/asyncpg).
4. Switch bot credentials to `DATABASE_URL`.
5. Switch site backend reads/writes to the same `DATABASE_URL`.
6. Deploy bot worker and verify:
   - registration
   - team management
   - tournament flows
   - payment flags
