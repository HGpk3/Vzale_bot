# Site Web (Frontend)

Production-style Next.js frontend for VZALE platform.

## Stack
- Next.js (App Router) + TypeScript
- Custom API client for `site_backend` (`/v1/*`)
- JWT session in localStorage with auto-refresh on 401
- Telegram-bot login flow (`start -> confirm in bot -> finish`)

## Implemented Routes
- `/` - landing (позиционирование VZALE + ключевые CTA)
- `/join` - onboarding для новых игроков
- `/login`
- `/public/tournaments`
- `/public/tournaments/[id]`
- `/dashboard`
- `/tournaments`
- `/tournaments/[id]`
- `/my/team`
- `/my/achievements`
- `/my/stats`
- `/admin`
- `/admin/tournaments/[id]`

## Run local
```bash
cd site_web
npm install
npm run dev
```

Set API URL if needed:
```bash
export NEXT_PUBLIC_API_URL='http://127.0.0.1:8100'
export NEXT_PUBLIC_BOT_USERNAME='vzalebb_bot'
```

## Docker
Frontend is included in root `docker-compose.yml` as service `web` on port `3000`.
