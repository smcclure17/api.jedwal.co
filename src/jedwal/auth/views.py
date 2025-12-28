from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from jedwal.account.models import AccountRead
from jedwal.common.encryption.service import Encryption
from jedwal.config import settings
from jedwal.database.core import DbTable

from .oauth import oauth
from .service import CurrentAccount, authenticate

auth_router = APIRouter(tags=["auth"])


@auth_router.get("/login")
async def login(request: Request):
    """Initiate OAuth flow with Google."""
    redirect_uri = f"{settings.api_base_url}/auth"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline"
    )


@auth_router.get("/auth")
async def auth(request: Request, table: DbTable, encryption: Encryption):
    """OAuth callback - complete authentication."""
    await authenticate(table=table, request=request, encryption=encryption)
    return RedirectResponse(url=settings.client_app_base_url)


@auth_router.get("/logout")
async def logout(request: Request):
    request.session.pop("account", None)
    return RedirectResponse(url=settings.client_base_url)


@auth_router.get("/me", response_model=AccountRead)
async def get_me(current_account: CurrentAccount):
    """Get current authenticated account"""
    return AccountRead.from_account(current_account)


# TODO: implement Google Picker Token routes if it
# seems like they actually improve the UX at all
