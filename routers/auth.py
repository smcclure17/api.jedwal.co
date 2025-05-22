"""
Authentication routes and OAuth configuration.
"""

import logging
import time
from fastapi import APIRouter, Body, HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth, OAuthError

from dependencies import CurrentUser
from sheetsapi import config, user_helpers
from sheetsapi.account_repo import AccountRepo
from sheetsapi.models.domain_models import UserSession

logger = logging.getLogger(__name__)

account_repo = AccountRepo.from_table_name()

router = APIRouter(tags=["auth"])

# OAuth configuration
oauth = OAuth(config.Config.to_starlette_config())

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
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
    if not user_token:
        raise HTTPException(
            status_code=500, detail=f"User data unexpectedly not found in auth token"
        )

    # access tokens are short-lived and never persisted, no need to encrypt
    user = UserSession(**user_token, access_token=token.get("access_token"))
    request.session["user"] = user.model_dump()

    refresh_token = token.get("refresh_token")
    existing_account = account_repo.get_account(user.sub)

    if existing_account is None:
        if refresh_token is None:
            raise HTTPException(
                f"No refresh token found but no account exists for user. "
                "Is it possible a user with a deleted account is trying to create a new one?"
            )
        logger.info(f"Creating new user for email: {user.email}")
        user_helpers.persist_user(user, refresh_token)
    return RedirectResponse(url=config.Config.Constants.CLIENT_APP_BASE_URL)


@router.get("/logout")
async def logout(request: Request):
    """
    Log out the user by clearing their session.
    """
    request.session.pop("user", None)
    return RedirectResponse(url=config.Config.Constants.CLIENT_BASE_URL)


@router.get("/google-picker-token")
async def get_token(user: CurrentUser):
    now = int(time.time())
    expired_token = user.picker_expires_at <= now
    if not user or not user.picker_token or not user.picker_expires_at or expired_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"token": user.picker_token}


@router.post("/google-picker-token")
async def save_token(request: Request, token=Body(...), expires_in=Body(...)):
    if "user" not in request.session:
        raise HTTPException(status_code=401, detail="Authentication required")

    now = int(time.time())
    expires_at = now + expires_in

    # Note -- these new session variables must match the names defined
    # in the UserSession model, else they will not be set correctly
    request.session["user"]["picker_token"] = token
    request.session["user"]["picker_expires_at"] = expires_at
    return {"message": "ok"}
