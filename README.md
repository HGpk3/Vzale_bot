# Vzale Platform

## Components
- `VZALE_BOT/` - Telegram bot service
- `site_backend/` - FastAPI backend for website/admin
- `site_web/` - Next.js frontend
- `docs/` - architecture, API, roadmap, runbooks

## Quick Start (Docker)
```bash
cp .env.example .env
# edit .env (set BOT_TOKEN)
docker compose up --build -d
```

Create the first website user:
```bash
docker compose exec api python scripts/create_web_user.py \
  --telegram-id 409436763 \
  --username admin \
  --password change_me_please \
  --database-url "postgresql://vzale:vzale_password@postgres:5432/vzale?sslmode=disable"
```

- API health: `http://127.0.0.1:8100/health`
- API docs: `http://127.0.0.1:8100/docs`
- Web app: `http://127.0.0.1:3000`

See full run guide: `docs/RUN_ALL.md`.


## AI handoff
- `docs/AI_HANDOFF_README.md`

## Handy Commands
- `make up` / `make down`
- `make logs`
- `make ps`
