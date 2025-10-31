from typing import Annotated
import logging
from fastapi import Depends, HTTPException, Request, status

from jedwal.account.models import Account, RefreshTokenInfo
from jedwal.common.encryption import EnvelopeEncryption
from .oauth import oauth
from .models import GoogleAccountSession
from jedwal.account.service import create_account, get_account, get_account_by_email
from jedwal.database.core import DbTable


from authlib.integrations.starlette_client import OAuthError

log = logging.getLogger(__name__)


async def authenticate(*, table: DbTable, request: Request):
    try:
        token: dict = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        request.session.pop("account", None)
        log.error(f"Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Something went wrong {e.error}",
        )

    user_token = token.get("userinfo")
    if not user_token:
        raise HTTPException(
            status_code=500, detail=f"User data unexpectedly not found in auth token"
        )

    # access tokens are short-lived and never persisted, no need to encrypt
    account_session = GoogleAccountSession(
        **user_token, access_token=token.get("access_token")
    )
    request.session["account"] = account_session.model_dump()

    refresh_token = token.get("refresh_token")
    existing_account = get_account(table=table, id=account_session.sub)

    if existing_account is None:
        if refresh_token is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No refresh token found but no account exists for user. "
                "Is it possible a user with a deleted account is trying to create a new one?",
            )

        encryption_response = EnvelopeEncryption.encrypt(
            refresh_token, context={"account_id": account_session.sub}
        )

        token_info = RefreshTokenInfo(
            encrypted_refresh_token=encryption_response.encrypted_data,
            data_encryption_key=encryption_response.encrypted_key,
            context=encryption_response.context,
        )
        account = Account(
            account_id=account_session.sub,
            account_status="free",
            display_name=Account.create_display_name(
                account_session.given_name, account_session.family_name
            ),
            email=account_session.email,
            family_name=account_session.family_name,
            given_name=account_session.given_name,
            refresh_token_info=token_info,
        )

        create_account(table=table, account=account)


def has_required_permissions(*, current_account: Account, account_id: str):
    # TODO: will require org check later (db lookup)
    return account_id == current_account.account_id


def get_current_account(*, table: DbTable, request: Request) -> Account:
    """Get currently authenticated account from session."""
    session_user = request.session.get("account")

    if session_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    account = get_account_by_email(table=table, email=session_user["email"])

    if account is None:
        raise HTTPException(status_code=401, detail="Account not found")

    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]
