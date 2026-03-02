.PHONY: up down logs ps restart test-api lint-api

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

restart:
	docker compose restart

test-api:
	cd site_backend && pytest -q

lint-api:
	cd site_backend && make lint
