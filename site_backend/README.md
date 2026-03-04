# Site Backend

## Run
```bash
cd site_backend
pip install -r requirements.txt
```

PowerShell:
```powershell
$env:DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
$env:ADMIN_IDS="409436763,469460286"
$env:JWT_SECRET="change-me-super-strong"
$env:BOT_LOGIN_SECRET="change-me-bot-login-secret"
$env:CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
uvicorn app.main:app --reload --port 8100
```

Bash:
```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require'
export ADMIN_IDS='409436763,469460286'
export JWT_SECRET='change-me-super-strong'
export BOT_LOGIN_SECRET='change-me-bot-login-secret'
export CORS_ORIGINS='http://localhost:3000,http://127.0.0.1:3000'
uvicorn app.main:app --reload --port 8100
```

## Auth model
- Production mode: use `Authorization: Bearer <access_token>`
- Dev fallback: `X-User-Id` header works only when `APP_ENV=dev`
- Admin endpoints require token/admin claim or `ADMIN_IDS`

## Implemented API
- `/health`
- `/v1/auth/*` (JWT + refresh rotation)
  - includes bot-login flow:
    - `POST /v1/auth/bot-login/start`
    - `GET /v1/auth/bot-login/status/{session_id}`
    - `POST /v1/auth/bot-login/confirm` (for bot)
    - `POST /v1/auth/bot-login/finish`
- `/v1/me/*`
- `/v1/tournaments/*`
- `/v1/teams/*`
- `/v1/matches/*`
- `/v1/admin/*`

Swagger: `http://127.0.0.1:8100/docs`

## Developer Commands
```bash
make lint
make test
make run
```

## Utility Scripts
Create or update web login user:
```bash
python scripts/create_web_user.py \
  --telegram-id 409436763 \
  --username admin \
  --password super_secret_password \
  --database-url "$DATABASE_URL"
```
