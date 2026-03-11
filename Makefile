SHELL := /bin/bash

.PHONY: up down logs health db-check run-once smoke

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker beat db redis

health:
	curl -sS http://localhost:8000/health && echo
	curl -sS http://localhost:8000/health/db && echo

db-check:
	docker compose exec api python -m odds_app.check_db

run-once:
	curl -sS -X POST "http://localhost:8000/admin/run-once?simulate_drop=false" && echo

smoke:
	docker compose exec api python -m odds_app.smoke_test --reset --simulate-drop
