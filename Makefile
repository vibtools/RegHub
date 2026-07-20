.PHONY: install dev lint test audit migrate seed run

install:
	python -m pip install -e ".[dev]"

dev:
	docker compose -f compose.local.yml up --build

lint:
	ruff check .
	ruff format --check .

test:
	pytest --cov=app --cov-report=term-missing

audit: lint test
	python -m compileall -q app scripts tests

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
