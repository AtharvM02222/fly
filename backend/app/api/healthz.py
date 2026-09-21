"""Health check endpoints."""

from typing import Dict

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from ..core.logging import get_logger
from ..db.session import get_session

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz")
async def health_check() -> Dict[str, str]:
    """
    Basic health check endpoint.

    Returns 200 OK if the service is running.
    """
    return {"status": "ok", "service": "dronecds-backend"}


@router.get("/readyz")
async def readiness_check(response: Response) -> Dict[str, str | Dict[str, str]]:
    """
    Readiness check endpoint.

    Verifies that the service can connect to required dependencies:
    - Database

    Returns:
        200 OK if all dependencies are ready
        503 Service Unavailable if any dependency is not ready
    """
    checks: Dict[str, str] = {}
    all_ready = True

    # Check database
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        logger.error(f"Database readiness check failed: {e}")
        checks["database"] = "failed"
        all_ready = False

    # TODO: Add Redis check once implemented
    # checks["redis"] = "ok"

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}

    return {"status": "ready", "checks": checks}
