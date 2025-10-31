from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from .service import authenticate
from .oauth import oauth
from jedwal.config import settings

auth_router = APIRouter()


@auth_router.get("/login")
async def login(request: Request):
    """Initiate OAuth flow with Google."""
    redirect_uri = f"{settings.api_base_url}/auth"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline"
    )


@auth_router.get("/auth")
async def auth(request: Request):
    """OAuth callback - complete authentication."""
    await authenticate(request=request)
    return RedirectResponse(url=settings.client_app_base_url)


@auth_router.get("/logout")
async def logout(request: Request):
    request.session.pop("account", None)
    return RedirectResponse(url=settings.client_base_url)
