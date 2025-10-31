"""API router configuration following Netflix Dispatch pattern."""

from fastapi import APIRouter
from jedwal.auth.views import auth_router
from jedwal.config.config import settings

# Main API router
api_router = APIRouter()


# Health check endpoint
@api_router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": settings.app_version}

api_router.include_router(auth_router)
