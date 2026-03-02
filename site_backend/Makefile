.PHONY: run test lint

run:
	uvicorn app.main:app --reload --port 8100

test:
	pytest -q

lint:
	python -m py_compile app/main.py app/config.py app/db.py app/deps.py app/http.py app/security.py app/routers/auth.py app/routers/users.py app/routers/tournaments.py app/routers/teams.py app/routers/matches.py app/routers/admin.py
