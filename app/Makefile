.PHONY: db-up db-down db-logs migrate migrate-down test dev seed eval

db-up:
	docker compose up -d

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

migrate:
	DATABASE_URL=$$(grep ^DATABASE_URL .env | cut -d= -f2-) uv run alembic upgrade head

migrate-down:
	DATABASE_URL=$$(grep ^DATABASE_URL .env | cut -d= -f2-) uv run alembic downgrade -1

test:
	uv run python -m pytest

dev:
	uv sync && PYTHONPATH=.. uv run uvicorn app.main:app --reload

seed:
	PYTHONPATH=.. uv run python -m app.scripts.seed_corpus

eval:
	PYTHONPATH=.. uv run python -m app.eval.run_eval
