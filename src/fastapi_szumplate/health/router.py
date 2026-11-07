"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str


@router.get("/health", operation_id="get_health")
async def get_health() -> HealthResponse:
    """Report that the service is alive."""
    return HealthResponse(status="ok")
