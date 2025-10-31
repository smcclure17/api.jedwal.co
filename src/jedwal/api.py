"""API router configuration."""

from fastapi import APIRouter, Depends
from jedwal.auth.service import get_current_account
from jedwal.auth.views import auth_router
from jedwal.account.views import account_router
from jedwal.config.config import settings

# Main API router
api_router = APIRouter()

authenticated_account_router = APIRouter(
    dependencies=[Depends(get_current_account)], prefix="/{account_id}"
)
authenticated_account_router.include_router(account_router)


# Health check endpoint
@api_router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": settings.app_version}


api_router.include_router(auth_router)
api_router.include_router(authenticated_account_router)
