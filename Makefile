.PHONY: install format lint typecheck test check run audit

install:
	uv sync --locked

format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run mypy

test:
	uv run pytest

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run coverage run -m pytest
	uv run coverage report

run:
	uv run uvicorn fastapi_szumplate.main:create_app --factory --reload

audit:
	uv export --locked --no-emit-project -o requirements.txt
	uvx pip-audit -r requirements.txt --disable-pip
