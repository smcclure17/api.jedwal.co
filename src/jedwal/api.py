"""API router configuration."""

from fastapi import APIRouter, Depends

from jedwal.account.views import account_router
from jedwal.analytics.views import authenticated_analytics_router
from jedwal.apis.views import authenticated_apis_router, public_apis_router
from jedwal.auth.service import verify_account_access
from jedwal.auth.views import auth_router
from jedwal.billing.views import billing_router
from jedwal.config.config import settings
from jedwal.emails.views import public_email_router
from jedwal.organizations.views import authenticated_organization_router
from jedwal.posts.views import authenticated_posts_router, public_posts_router

api_router = APIRouter()

authenticated_account_router = APIRouter(
    dependencies=[Depends(verify_account_access)], prefix="/manage/{account_id}"
)
authenticated_account_router.include_router(account_router)
authenticated_account_router.include_router(authenticated_apis_router)
authenticated_account_router.include_router(authenticated_posts_router)
authenticated_account_router.include_router(authenticated_organization_router)
authenticated_account_router.include_router(authenticated_analytics_router)

public_account_router = APIRouter(prefix="/{account_id}")
public_account_router.include_router(public_apis_router)
public_account_router.include_router(public_posts_router)


@api_router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": settings.app_version}


api_router.include_router(auth_router)
api_router.include_router(public_email_router)
api_router.include_router(authenticated_account_router)
api_router.include_router(public_account_router)
api_router.include_router(billing_router)
