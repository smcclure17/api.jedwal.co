import logging
from typing import Annotated

from authlib.integrations.starlette_client import OAuthError
from fastapi import Depends, HTTPException, Request, status

from jedwal.account.models import Account, RefreshTokenInfo
from jedwal.account.service import create_account, get_account, get_account_by_email
from jedwal.common.encryption import EnvelopeEncryption
from jedwal.database.core import DbTable
from jedwal.organizations.membership import service as membership_service

from .models import GoogleAccountSession
from .oauth import oauth

log = logging.getLogger(__name__)


# TODO: refactor this and pull out pieces into
async def authenticate(*, table: DbTable, request: Request):
    try:
        token: dict = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        request.session.pop("account", None)
        log.error(f"Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Something went wrong {e.error}",
        ) from e

    user_token = token.get("userinfo")
    if not user_token:
        raise HTTPException(
            status_code=500, detail="User data unexpectedly not found in auth token"
        ) from None

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
                detail="No refresh token found but no account exists for user. "
                "Is it possible a user with a deleted account is trying to create a new one?",
            ) from None

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


def get_current_account(*, table: DbTable, request: Request) -> Account:
    """Get currently authenticated account from session."""
    session_user = request.session.get("account")

    if session_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated") from None

    account = get_account_by_email(table=table, email=session_user["email"])

    if account is None:
        raise HTTPException(status_code=401, detail="Account not found") from None

    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]


def verify_account_access(
    *, table: DbTable, account_id: str, current_account: CurrentAccount
) -> Account:
    """Verify current account has permission to access the specified account."""
    if account_id == current_account.account_id:
        return current_account

    membership = membership_service.check_account_membership(
        table=table, account_id=current_account.account_id, organization_id=account_id
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this account",
        ) from None
    return current_account


VerifiedAccount = Annotated[Account, Depends(verify_account_access)]


def verify_user_account(
    *, table: DbTable, account_id: str, current_account: CurrentAccount
) -> Account:
    """Verify account_id is a USER account (not org) and current user has access."""
    verify_account_access(
        table=table, account_id=account_id, current_account=current_account
    )

    # Then verify it's actually a user
    account = get_account(table=table, id=account_id)
    if account is None:
        raise HTTPException(
            status_code=400,
            detail="This operation requires a user account, not an organization",
        ) from None

    return account
