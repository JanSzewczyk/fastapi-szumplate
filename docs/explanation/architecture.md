# Architecture

## Domain first, layers inside

Top-level packages are business areas (`health`, `library/books`, `library/loans`); the layers
(router, schemas, service, repository) sit inside each. A change to "loans" edits one folder.

## Two module shapes, one rule for choosing

- **Default shape** (`books`, `health`): router, schemas, models, service, repository. The service
  is a few lines; the only rule is "an ISBN is unique".
- **Hexagonal shape** (`loans`): `domain/` holds `Loan.lend` and `Loan.give_back` and imports
  nothing but the standard library; `domain/ports.py` declares what the module needs;
  `service_layer/` gathers facts and calls the domain; `adapters/` implement the ports;
  `entrypoints/` is the HTTP side.

Structure is added to one module at a time, when it hurts. Do not convert `books` to match
`loans`.

## Import direction

Routers depend on services, services on the domain and its ports, adapters on the domain. The
domain imports no web framework, no ORM, no adapter. Only `dependencies.py`, `library/__init__.py`
and `main.py` import adapters. Modules refer to one another by id and never import each other's
models: `loans` asks `books` for one number (the capacity) through
`loans/adapters/books_catalog.py`. `make imports` enforces all of this.

## The core never knows the example

`main.py` calls `include_library(app)`; nothing else outside `library/` mentions it. That is what
makes the example removable as a unit.

## Wiring

`create_app(settings)` builds the app and configures logging once. Repositories are built once, in
`include_library`, and stored on `app.state`. Dependencies read them from the request, so tests
replace them with `app.dependency_overrides` and the app never has module-level state.

## Why handlers are sync `def`

Routes run in Starlette's threadpool. The example does no async I/O, and plain `def` makes the
parallel tests meaningful: concurrent requests really run at the same time. Switch a route to
`async def` only when it awaits something, and then give each awaited call a timeout.

## Strict input without surprises

Pydantic's lax mode reads `0` as `1970-01-01` and `"3"` as `3`, which the spec does not allow.
Dates use `IsoDate` and integers use `WholeNumber` (a whole number, written `3` or `3.0`, never a
string or a bool). Whole-model strict mode was rejected because it also refuses valid date and UUID
strings.

## Concurrency

A rule that reads before it writes is guarded by one atomic step, and each guard has a parallel
test that fails without it. See [add-a-module](../how-to/add-a-module.md) and
[swap-in-a-database](../how-to/swap-in-a-database.md).
