"""
Authentication routes and OAuth configuration.
"""

import logging
from fastapi import APIRouter, HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth, OAuthError

from sheetsapi import config, user_helpers
from sheetsapi.models.domain_models import UserSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# OAuth configuration
oauth = OAuth(config.Config.to_starlette_config())

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "openid",
    "profile",
    "email",
]

OATH_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

oauth.register(
    name="google",
    server_metadata_url=OATH_METADATA_URL,
    client_kwargs={"scope": " ".join(OAUTH_SCOPES)},
)


@router.get("/login")
async def login(request: Request):
    """
    Start the OAuth login flow with Google.
    Redirects to Google for authentication.
    """
    redirect_uri = f"{config.Config.Constants.API_BASE_URL}/auth"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline"
    )


@router.get("/auth")
async def auth(request: Request):
    """
    Handle the OAuth callback from Google.
    Stores user information in the session.
    """
    try:
        token: dict = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        request.session.pop("user", None)
        logger.error(f"Error: {e.error}")
        raise HTTPException(status_code=500, detail=f"Something went wrong {e.error}")
    user_token = token.get("userinfo")
    if user_token:
        user = UserSession(
            **user_token,
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
        )
        request.session["user"] = user.model_dump()

    user_helpers.persist_user_if_not_exists(user)
    return RedirectResponse(url=config.Config.Constants.CLIENT_APP_BASE_URL)


@router.get("/logout")
async def logout(request: Request):
    """
    Log out the user by clearing their session.
    """
    request.session.pop("user", None)
    request.session.pop("refresh_token", None)
    return RedirectResponse(url=config.Config.Constants.CLIENT_BASE_URL)
