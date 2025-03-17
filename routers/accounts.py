"""User-related routes and operations."""

from fastapi import APIRouter, Query, Response
import fastapi
from typing import Optional
from fastapi.responses import RedirectResponse

from sheetsapi import sheet_api_repo_v2
from sheetsapi.models.api_models import UserDataResponse
from sheetsapi.config import Config
from dependencies import CurrentUser

router = APIRouter(tags=["users"])
api_v2_manager = sheet_api_repo_v2.SheetApiRepo.from_table_name()


@router.get("/get-account-data", response_model=UserDataResponse)
async def get_account_data(user: CurrentUser, account_id: str | None = None):
    """
    Get information about the currently authenticated user.

    Returns:
        UserDataResponse: User profile and account information
    """

    if account_id and not api_v2_manager.check_user_access_for_owner(
        user.sub, account_id
    ):
        raise fastapi.HTTPException(status_code=403, detail="Not authorized")

    if not account_id:
        account_id = user.sub

    user_item = api_v2_manager.get_account(account_id)
    if user_item is None:
        raise fastapi.HTTPException(
            status_code=404,
            detail=f"User not found, id: {account_id}",
        )

    try:
        org_memberships = api_v2_manager.get_org_memberships_for_user(
            user_item["account_id"]
        )
    except sheet_api_repo_v2.UserNotFoundError:
        org_memberships = []  # account is an organization so it has no orgs

    orgs = api_v2_manager.get_accounts([org["org_id"] for org in org_memberships])
    return UserDataResponse(
        id=user_item["account_id"],
        email=user.email,
        display_name=user_item["display_name"],
        account_status=user_item["account_status"],
        sheet_apis=api_v2_manager.get_sheet_apis_for_account(user.sub),
        orgs=orgs,
        type=user_item["type"],
    )


@router.get("/unsubscribe")
async def unsubscribe(user_id: str = Query(...), redirect: bool = Query(True)):
    """
    Unsubscribe a user from emails.

    Args:
        user_id: The ID of the user to unsubscribe
        email: The email address to unsubscribe (used if user_id is not provided)
        redirect: If True, redirect to a confirmation page; otherwise return JSON

    Returns:
        JSON response or redirect to confirmation page
    """

    success = False
    user_item = api_v2_manager.get_account(user_id)
    if user_item:
        # Set unsubscribed flag to True
        api_v2_manager.update_account(user_id, {"unsubscribed": True})
        success = True

    if not success:
        if redirect:
            # Redirect to error page
            return RedirectResponse(
                url=f"{Config.Constants.CLIENT_BASE_URL}/unsubscribe-error"
            )
        else:
            return {"success": False, "message": "User not found"}

    if redirect:
        # Redirect to success page
        return RedirectResponse(
            url=f"{Config.Constants.CLIENT_BASE_URL}/unsubscribe-success"
        )
    else:
        return {"success": True, "message": "Successfully unsubscribed"}
