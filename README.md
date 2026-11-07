# fastapi-szumplate

Production-ready FastAPI starter template by Szum-Tech: uv, Ruff, mypy (strict), pytest with coverage, and GitHub Actions CI.

## Getting started

Click **Use this template** on GitHub, then:

```bash
cp .env.example .env
make install
make run
```

The API runs on http://127.0.0.1:8000, docs at `/docs`.

After creating a project from the template, rename `fastapi_szumplate` (the `src/` package, `pyproject.toml`, `Makefile`).

## Commands

| Command | Purpose |
| --- | --- |
| `make install` | Install locked dependencies |
| `make run` | Start the dev server with reload |
| `make format` / `make lint` / `make typecheck` | Ruff format, Ruff lint, mypy |
| `make test` | Run pytest |
| `make check` | Everything CI runs |
| `make audit` | Dependency vulnerability audit |

## Structure

```
src/fastapi_szumplate/
  main.py      # app factory
  config.py    # settings from env
  health/      # example domain package: router
tests/
```

## License

MIT
