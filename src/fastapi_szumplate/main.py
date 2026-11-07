"""Application factory."""

import logging

from fastapi import FastAPI

from fastapi_szumplate.config import Settings
from fastapi_szumplate.health.router import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Optional settings override, used by tests.

    Returns:
        The configured application.
    """
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(title=settings.app_name)
    app.include_router(health_router)
    return app
