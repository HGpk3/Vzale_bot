# Architecture

## Current (stabilized)
- Entrypoint: `VZALE_BOT/app/main.py`
- Runtime bot logic: `VZALE_BOT/bot_with_broadcast_poll.py`
- DB migration scripts: `VZALE_BOT/scripts/`
- SQL schema: `VZALE_BOT/sql/`
- Docs: `docs/`

## Why this layout
- Single canonical entrypoint for local/dev/prod.
- Infrastructure files (SQL/scripts/docs) are separated from runtime bot code.
- Easy transition from SQLite to PostgreSQL without breaking deployment.

## Next refactor steps (safe sequence)
1. Split DB operations from `bot_with_broadcast_poll.py` into `VZALE_BOT/app/db/`.
2. Move keyboard builders into `VZALE_BOT/app/keyboards/`.
3. Move handlers by domain into `VZALE_BOT/app/handlers/`:
   - `user.py`
   - `admin.py`
   - `stats.py`
   - `achievements.py`
4. Keep `bot_with_broadcast_poll.py` as compatibility shim during migration, then remove.
