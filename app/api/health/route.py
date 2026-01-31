"""
Health check stub for API sanity checks.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", name="Health check")
async def health():
    """Return ok for readiness/health checks."""
    return {"status": "ok"}
