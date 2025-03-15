"""User-related routes and operations."""

from fastapi import APIRouter
import fastapi

from sheetsapi import sheet_api_repo_v2
from sheetsapi.models.api_models import UserDataResponse
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
