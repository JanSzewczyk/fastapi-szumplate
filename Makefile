.PHONY: install hooks format lint typecheck imports test check run openapi openapi-check api-lint \
	api-breaking schemathesis api-check audit docker-build docker-run clean
.PHONY: smoke-template  # only:template

SPECTRAL := npx --yes @stoplight/spectral-cli@6.17.1
OASDIFF_IMAGE := tufin/oasdiff:v1.35.0
BASE_SPEC := .openapi-base.json

install:
	uv sync --locked

hooks:
	uv run pre-commit install

format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run mypy

imports:
	uv run lint-imports

test:
	uv run pytest

# The one command CI runs: format, lint, types, import contracts, tests with coverage, spec drift.
check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run lint-imports
	uv run coverage run -m pytest
	uv run coverage report
	$(MAKE) openapi-check

run:
	uv run python -m fastapi_szumplate

# openapi.json is generated from the app; never edit it by hand.
openapi:
	uv run python scripts/export_openapi.py

openapi-check:
	uv run python scripts/export_openapi.py --check

api-lint:
	$(SPECTRAL) lint openapi.json --fail-severity=warn

# Compare with the spec on origin/main; breaking changes (errors) fail. Needs oasdiff or Docker.
api-breaking:
	@if ! git cat-file -e origin/main:openapi.json 2>/dev/null; then \
		echo "origin/main has no openapi.json yet; skipping the breaking-change check."; exit 0; \
	fi; \
	git show origin/main:openapi.json > $(BASE_SPEC); \
	if command -v oasdiff >/dev/null 2>&1; then \
		oasdiff breaking $(BASE_SPEC) openapi.json --fail-on ERR; \
	else \
		docker run --rm -v "$(CURDIR):/spec:ro" $(OASDIFF_IMAGE) \
			breaking /spec/$(BASE_SPEC) /spec/openapi.json --fail-on ERR; \
	fi

# Starts the service, runs Schemathesis with every check and phase, stops the service.
schemathesis:
	scripts/run_schemathesis.sh

api-check: openapi-check api-lint api-breaking schemathesis

audit:
	uv export --locked --no-emit-project -o requirements.txt
	uvx pip-audit -r requirements.txt --disable-pip

docker-build:
	docker build -t fastapi-szumplate:local .

# Needs a .env (cp .env.example .env). HOST and PORT are forced: the server must listen on 0.0.0.0.
docker-run:
	docker run --rm -p 8000:8000 --read-only --tmpfs /tmp --env-file .env \
		-e HOST=0.0.0.0 -e PORT=8000 fastapi-szumplate:local

# begin:template
# Builds projects from this template in a temp dir, with and without the example, and runs their
# gates (uv sync --locked, make openapi, make check). Slow: it installs two environments.
smoke-template:
	scripts/smoke_template.sh
	scripts/smoke_template.sh --rename-only

# end:template
clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache .hypothesis .coverage requirements.txt $(BASE_SPEC)
	find . -name __pycache__ -type d -prune -not -path "./.venv/*" -exec rm -rf {} +
