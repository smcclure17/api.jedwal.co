"""User-related routes and operations."""

from fastapi import APIRouter, Query
import fastapi
from fastapi.responses import RedirectResponse

from sheetsapi.account_repo import AccountRepo, UserNotFoundError
from sheetsapi.models.api_models import UserDataResponse
from sheetsapi.config import Config
from dependencies import CurrentUser
from sheetsapi.sheet_repo import SheetApiRepo

router = APIRouter(tags=["users"])
account_repo = AccountRepo.from_table_name()
sheet_repo = SheetApiRepo.from_table_name()


@router.get("/get-account-data", response_model=UserDataResponse)
async def get_account_data(user: CurrentUser, account_id: str | None = None):
    """
    Get information about the currently authenticated user.

    Returns:
        UserDataResponse: User profile and account information
    """
    if account_id and not account_repo.check_user_access_for_owner(
        user.sub, account_id
    ):
        raise fastapi.HTTPException(status_code=403, detail="Not authorized")

    if not account_id:
        account_id = user.sub
    print(account_id)

    user_item = account_repo.get_account(account_id)
    if user_item is None:
        raise fastapi.HTTPException(
            status_code=404,
            detail=f"User not found, id: {account_id}",
        )

    try:
        org_memberships = account_repo.get_org_memberships_for_user(
            user_item["account_id"]
        )
    except UserNotFoundError:
        org_memberships = []  # account is an organization so it has no orgs

    orgs = account_repo.get_accounts([org["org_id"] for org in org_memberships])
    return UserDataResponse(
        id=user_item["account_id"],
        email=user.email,
        display_name=user_item["display_name"],
        account_status=user_item["account_status"],
        sheet_apis=sheet_repo.get_apis_for_account(user.sub),
        orgs=orgs,
        type=user_item["type"],
    )


@router.get("/unsubscribe")
async def unsubscribe(user_id: str = Query(...)):
    """
    Unsubscribe a user from emails.

    Args:
        user_id: The ID of the user to unsubscribe
        email: The email address to unsubscribe (used if user_id is not provided)
        redirect: If True, redirect to a confirmation page; otherwise return JSON

    Returns:
        JSON response or redirect to confirmation page
    """

    try:
        user_item = account_repo.get_account(user_id)
        if user_item is None:
            raise UserNotFoundError(f"user {user_id} not found")
        account_repo.update_account(user_id, {"unsubscribed": True})
    except Exception:
        return RedirectResponse(
            url=f"{Config.Constants.CLIENT_BASE_URL}/unsubscribe-error"
        )
    return RedirectResponse(
        url=f"{Config.Constants.CLIENT_BASE_URL}/unsubscribe-success"
    )
