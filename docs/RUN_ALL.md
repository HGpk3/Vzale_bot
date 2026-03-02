# Run All Services

## Option A: Docker (recommended)

1. Create local env file:
```bash
cp .env.example .env
```

2. Set real values in `.env`:
- `BOT_TOKEN`
- optional: `POSTGRES_*`, `ADMIN_IDS`, `JWT_SECRET`

3. Build and start:
```bash
docker compose up --build -d
```

4. Health checks:
- API health: `http://127.0.0.1:8100/health`
- API docs: `http://127.0.0.1:8100/docs`

5. Create first site login user:
```bash
docker compose exec api python scripts/create_web_user.py \
  --telegram-id 409436763 \
  --username admin \
  --password change_me_please \
  --database-url "postgresql://${POSTGRES_USER:-vzale}:${POSTGRES_PASSWORD:-vzale_password}@postgres:5432/${POSTGRES_DB:-vzale}?sslmode=disable"
```

6. Stop:
```bash
docker compose down
```

7. Stop + remove DB volume:
```bash
docker compose down -v
```

## Data migration inside Docker Postgres

If you need to import data from `VZALE_BOT/tournament.db` into local docker postgres:

```bash
docker compose run --rm bot python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path tournament.db \
  --schema-path sql/postgres_schema.sql \
  --postgres-url "postgresql://${POSTGRES_USER:-vzale}:${POSTGRES_PASSWORD:-vzale_password}@postgres:5432/${POSTGRES_DB:-vzale}?sslmode=disable" \
  --truncate
```

## Option B: Manual local run

### 1) Bot
```bash
cd VZALE_BOT
pip install -r requirements.txt
```

PowerShell:
```powershell
$env:DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
python -m app.main
```

### 2) Site Backend API
```bash
cd site_backend
pip install -r requirements.txt
```

PowerShell:
```powershell
$env:DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
$env:ADMIN_IDS="409436763,469460286"
uvicorn app.main:app --reload --port 8100
```

### 3) Site Web
Current repository has frontend architecture/spec scaffold only (`site_web/README.md`).
Backend is production-ready baseline; frontend implementation is next sprint scope.

## Smoke checks
- Bot starts without DB errors
- `GET http://127.0.0.1:8100/health` returns `status=ok`
- Open Swagger: `http://127.0.0.1:8100/docs`
- Call protected endpoint with header `X-User-Id`

## Refresh token maintenance
Admin can manually cleanup old refresh tokens:
```bash
curl -X POST "http://127.0.0.1:8100/v1/auth/cleanup-refresh" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{"retention_days":30}'
```
