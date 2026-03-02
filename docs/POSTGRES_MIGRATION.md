# PostgreSQL Migration

## Canonical bot file
Only use: `VZALE_BOT/bot_with_broadcast_poll.py`.

## Why this is needed
SQLite is file-based and does not work reliably when bot and site are hosted separately and write concurrently.
PostgreSQL is a shared server database and is safe for this scenario.

## 1) Create PostgreSQL database
Use any managed provider (Neon/Supabase/Render Postgres).

You need a connection string like:
`postgresql://USER:PASSWORD@HOST:5432/DBNAME`

## 2) Install migration dependency
From repo root:

```bash
pip install psycopg[binary]
```

Or via project requirements (updated):

```bash
pip install -r VZALE_BOT/requirements.txt
```

## 3) Apply schema only (optional test)
```bash
python3 VZALE_BOT/scripts/migrate_sqlite_to_postgres.py \
  --postgres-url "postgresql://..." \
  --schema-only
```

## 4) Full data migration from SQLite to Postgres
```bash
python3 VZALE_BOT/scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path VZALE_BOT/tournament.db \
  --postgres-url "postgresql://..." \
  --truncate
```

`--truncate` clears existing target tables before copy.

## 5) Current status of application code
Migration tooling is ready (schema + data transfer).

Bot now has a compatibility DB layer (`VZALE_BOT/app/db_compat.py`):
- if `DATABASE_URL` is set -> PostgreSQL mode
- if `DATABASE_URL` is not set -> SQLite mode

This allows gradual query cleanup without downtime.
