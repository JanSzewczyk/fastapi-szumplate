"""Application factory."""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from fastapi_szumplate.config import Settings
from fastapi_szumplate.health.readiness import install_readiness
from fastapi_szumplate.health.router import router as health_router
from fastapi_szumplate.library import include_library
from fastapi_szumplate.logging_config import configure_logging
from fastapi_szumplate.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from fastapi_szumplate.openapi import HEALTH_TAG, METADATA, install_openapi
from fastapi_szumplate.problems import add_problem_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Optional settings override, used by tests.

    Returns:
        The configured application.
    """
    settings = settings or Settings()
    configure_logging(settings)
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        redirect_slashes=False,
        openapi_tags=[HEALTH_TAG],
        **METADATA,
    )
    app.state.settings = settings
    add_problem_handlers(app)
    install_openapi(app)
    install_readiness(app)
    app.include_router(health_router)
    include_library(app)  # the example domain; remove this line and the import to drop it

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
