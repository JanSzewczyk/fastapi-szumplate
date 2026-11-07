# fastapi-szumplate

A copy-ready FastAPI service template by Szum-Tech: typed settings, structured logging, one error
format (Problem Details), a generated and checked OpenAPI contract, an example domain you can
delete, Docker, pre-commit and CI. Python 3.15, uv, Ruff, mypy (strict), pytest.

<!-- begin:template -->
## Use it

Click **Use this template** on GitHub, clone your copy, then rename it and (optionally) drop the
example domain:

```bash
python scripts/init_project.py orders-api                    # keep the example
python scripts/init_project.py orders-api --without-example  # start from the bare service
uv sync && make openapi && make check
```

The script renames the distribution, the package, its directory and every mention of the old
name. Review the contact URL in `src/<package>/openapi.py` afterwards.

<!-- end:template -->
## Run it

```bash
cp .env.example .env
make install
make run          # python -m fastapi_szumplate
```

The API listens on http://127.0.0.1:8000. With `DOCS_ENABLED=true` (set in `.env.example`) the
interactive docs are at `/docs` and the spec at `/openapi.json`; they are **off by default**.

Start it with `python -m fastapi_szumplate`, not with the `uvicorn` command. The module
configures logging once and tells uvicorn to leave it alone (`log_config=None`) and to skip its own
access log. If you must use the CLI, pass `--factory` (`uvicorn fastapi_szumplate.main:create_app
--factory`); you then get uvicorn's default log format next to ours.

## Commands

| Command | Purpose |
| --- | --- |
| `make install` | Install locked dependencies (`uv sync --locked`) |
| `make hooks` | Install the pre-commit hooks |
| `make run` | Start the service (`python -m fastapi_szumplate`) |
| `make format` | Ruff format |
| `make lint` | Ruff lint |
| `make typecheck` | mypy, strict |
| `make imports` | import-linter contracts (module boundaries) |
| `make test` | pytest |
| `make check` | What CI runs: format check, lint, mypy, import contracts, tests with coverage, OpenAPI drift |
| `make openapi` | Regenerate `openapi.json` from the app (never edit it by hand) |
| `make openapi-check` | Fail if `openapi.json` is out of date |
| `make api-lint` | Spectral on `openapi.json`, failing on warnings (needs Node; runs `npx`) |
| `make api-breaking` | oasdiff against `origin/main:openapi.json`, failing on breaking changes (needs oasdiff or Docker) |
| `make schemathesis` | Start the service, run Schemathesis with every check and phase, stop it |
| `make api-check` | `openapi-check`, `api-lint`, `api-breaking` and `schemathesis` |
| `make audit` | pip-audit on the locked dependencies |
| `make docker-build` / `make docker-run` | Build and run the image (needs Docker and a `.env`) |
| `make smoke-template` | Build projects from the template in a temp dir, with and without the example, and run their gates (slow) | <!-- only:template -->
| `make clean` | Remove caches and generated files |

Parallel-guard tests carry the `concurrency` marker: `uv run pytest -m concurrency`.

## What is inside

```text
src/fastapi_szumplate/
  main.py            create_app(settings): wiring only; include_library(app) is the one example hook
  __main__.py        python -m fastapi_szumplate
  config.py          Settings (pydantic-settings), get_settings dependency
  logging_config.py  structlog on stdlib: JSON or console, redaction, idempotent
  middleware.py      request id, bound log context, one access-log line per request
  problems.py        Problem Details model, handlers for 404/405/422/500, domain error mapping
  openapi.py         API metadata and the document clean-up
  types.py           IsoDate, IsoAwareDatetime, WholeNumber
  pagination.py      Page[T] envelope and limit/offset parameters
  health/            GET /health (liveness), GET /health/ready (readiness, 503 problem)
  library/           THE EXAMPLE DOMAIN, removable as a unit
    books/           default module shape: router, schemas, models, service, repository
    loans/           hexagonal shape: domain, ports, service layer, adapters, entrypoints
tests/               mirrors src; tests/library/ holds the example's tests
scripts/             export_openapi.py, init_project.py, run_schemathesis.sh
docs/                how-to guides, reference, explanation
```

Two module shapes are shown on purpose. Start every module like `books` (router, schemas, models,
service, repository). Move one to the `loans` shape (domain objects, ports, adapters) only when
its rules grow enough to hurt; see [docs/explanation/architecture.md](docs/explanation/architecture.md).

The example is a small library: books with a fixed number of copies, and loans with six rules
(unique ISBN, a free copy, three active loans per member, no repeat borrow, return once, not
before the borrow date). Each state-dependent rule answers 409 with its own problem type and has a
parallel test that fails when the guard is removed. Storage is in memory behind a repository port.

## Errors

Every error is `application/problem+json` (RFC 9457) with `type`, `title`, `status`, `detail` and,
when known, `request_id`. Validation errors add `errors` with only `loc`, `msg` and `type`; the
submitted value is never echoed. Clients branch on `type`. See
[docs/reference/problem-types.md](docs/reference/problem-types.md).

A 500 is answered by `UnhandledErrorMiddleware`, the innermost middleware, so it carries the
`X-Request-ID` header and, when CORS is on, the CORS headers (checked against uvicorn). The body is
the generic problem with the `request_id`; the traceback is logged once, on the `request_completed`
line of that request, without local variables. Known limits: if the application fails after the
response has started, the status and headers are already sent and cannot be replaced, so the
server cuts the connection and logs the traceback itself; a failure in the middleware themselves is
answered by Starlette's backstop handler, still the generic problem but without `X-Request-ID` or
CORS headers. A refused CORS preflight is a 400 problem too; a successful preflight is Starlette's
bodyless `OK` (`text/plain`), which is not an error.

## Configuration

All settings come from the environment or `.env` (see `.env.example`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_NAME` | `fastapi-szumplate` | API title |
| `ENVIRONMENT` | `local` | `local`, `test` or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG` to `CRITICAL` |
| `LOG_FORMAT` | `auto` | `json`, `console`, or `auto` (console when `local`, otherwise JSON) |
| `DOCS_ENABLED` | `false` | Serve `/docs`, `/redoc`, `/openapi.json` |
| `CORS_ORIGINS` | `[]` | JSON list of allowed origins; empty turns CORS off |
| `HOST`, `PORT`, `RELOAD` | `127.0.0.1`, `8000`, `false` | Server binding |
| `DEFAULT_PAGE_SIZE` | `20` | Page size when `limit` is omitted |
| `LOANS_MAX_ACTIVE_PER_MEMBER`, `LOAN_DAYS` | `3`, `14` | Example domain only |

Authentication is out of scope for the template. Put it in a dependency on the routers you want to
protect, and publish the security scheme in the OpenAPI document.

## Removing the example

Run `python scripts/init_project.py <name> --without-example`, or follow
[docs/how-to/remove-the-example.md](docs/how-to/remove-the-example.md) by hand. CI proves on every
change that a copy without the example still passes `make check`.

## Docker

```bash
make docker-build
make docker-run
```

The image is multi-stage, runs as a non-root user and has a health check. `compose.yaml` runs it
with a read-only filesystem. Docker is not required for development.

## CI

`.github/workflows/ci.yml` runs on push, pull request and weekly: `check` (`make check` and the
dependency audit), `api` (Spectral, oasdiff, Schemathesis), `docker` (build and call `/health`),
`template-smoke` (rename, remove the example, `make check`) and an informational free-threaded
Python job that never blocks a merge.

## License

MIT
