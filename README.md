# Vzale Bot

## Repository Structure
- `VZALE_BOT/` - bot application (runtime code)
- `VZALE_BOT/app/main.py` - canonical entrypoint
- `VZALE_BOT/bot_with_broadcast_poll.py` - current bot logic (legacy monolith)
- `VZALE_BOT/scripts/` - operational scripts (migrations, maintenance)
- `VZALE_BOT/sql/` - database schema files
- `docs/` - architecture and migration docs

## Run Bot Locally
```bash
cd VZALE_BOT
pip install -r requirements.txt
python -m app.main
```

## Database Mode
- If `DATABASE_URL` is set, bot uses PostgreSQL.
- If `DATABASE_URL` is not set, bot uses local SQLite file `tournament.db`.

## PostgreSQL Migration
See: `docs/POSTGRES_MIGRATION.md`.
