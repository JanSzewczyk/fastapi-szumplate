"""Application factory."""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from fastapi_szumplate.config import Settings
from fastapi_szumplate.health.router import router as health_router
from fastapi_szumplate.logging_config import configure_logging
from fastapi_szumplate.middleware import REQUEST_ID_HEADER, RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Optional settings override, used by tests.

    Returns:
        The configured application.
    """
    settings = settings or Settings()
    configure_logging(settings)
    app = FastAPI(title=settings.app_name)
    app.state.settings = settings
    app.include_router(health_router)

    # Starlette makes the last middleware added the outermost one.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=[REQUEST_ID_HEADER, "Content-Type"],
            expose_headers=[REQUEST_ID_HEADER],
            allow_credentials=False,
        )
    app.add_middleware(RequestContextMiddleware)
    return app
