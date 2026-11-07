# Changelog

All notable changes to this template are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

<!-- begin:template -->
### Added

- Typed settings (`ENVIRONMENT`, `LOG_LEVEL`, `LOG_FORMAT`, `DOCS_ENABLED`, `CORS_ORIGINS`, server
  binding, paging and example-domain limits) with a documented `.env.example`.
- Structured logging with structlog on stdlib: JSON or console output, key redaction, one access
  log line per request and an `X-Request-ID` header bound to every log line.
- `python -m fastapi_szumplate` entry point.
- Problem Details (RFC 9457) for every error: 404, 405 with `Allow`, validation (only `loc`, `msg`,
  `type`), 400 and a generic 500; one stable `type` per domain error.
- Generated, committed and drift-checked `openapi.json`; contract tests for it; Spectral rules,
  oasdiff and Schemathesis targets.
- Liveness (`/health`) and readiness (`/health/ready`) endpoints.
- Example domain under `library/` (books and loans) with six rules, atomic guards and parallel
  tests; in-memory repositories behind ports with a shared contract suite.
- import-linter contracts for module boundaries.
- Multi-stage Dockerfile, `compose.yaml`, pre-commit configuration and Dependabot.
- CI jobs for the contract tooling, the image, a template smoke test and an informational
  free-threaded Python run.
- `scripts/init_project.py` to rename a copy and optionally remove the example.
- Documentation: how-to guides, problem type reference and architecture notes.

### Fixed

- Logged tracebacks no longer include local variables: a frame's `scope` holds the request
  headers, `Authorization` included. The console format uses the plain traceback formatter.
- A 500 now carries the `X-Request-ID` header and the CORS headers: the catch-all moved from
  Starlette's outermost middleware into `UnhandledErrorMiddleware`, and the traceback is logged
  once, on the `request_completed` line.
- The ISBN pattern is `^[0-9]{13}$`: non-ASCII digits (Arabic-Indic, fullwidth) were accepted
  because the regex engine reads `\d` as any Unicode digit, so one ISBN could be stored twice.
- A refused CORS preflight is a Problem Details 400, not plain text.
- A JSON body with an integer of more than 4300 digits is a 422 `json_invalid`, not a 400. Only
  FastAPI's own body-parsing 400 is reclassified: a 400 that application code raises from a
  `ValueError` keeps its status and detail.

### Changed

- Dependency floors raised to the locked versions; CI actions pinned to verified versions.
- Coverage threshold raised from 90 to 95.
<!-- end:template -->
