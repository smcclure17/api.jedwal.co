"""Organization management routes and operations."""

import logging

from fastapi import APIRouter, Body, HTTPException
from pydantic import EmailStr

from sheetsapi import sheet_api_repo_v2
from sheetsapi.models.api_models import (
    CreateOrganizationRequest,
    OrganizationResponse,
)
from dependencies import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["organizations"])
api_manager_v2 = sheet_api_repo_v2.SheetApiRepo.from_table_name()


@router.post("/create-organization", response_model=OrganizationResponse)
async def create_organization(data: CreateOrganizationRequest, user: CurrentUser):
    """
    Create a new organization.
    The current user will automatically be added as an admin of the organization.

    Args:
        name: The name of the organization

    Returns:
        OrganizationResponse: The newly created organization
    """
    result = api_manager_v2.create_organization(
        org_name=data.name, created_by=user.sub, members=data.invitees
    )
    org_id = result["account_id"]
    created_at = result["created_at"]
    created_by = result["created_by"]

    return OrganizationResponse(
        id=org_id, name=data.name, created_at=created_at, created_by=created_by
    )


@router.post("/invite-users-to-organization")
async def invite_users(
    org_id: str = Body(...), user_emails: list[EmailStr] = Body(...)
):
    # This sucks but whatever
    members = api_manager_v2.get_users_for_org(org_id)
    member_ids = {m["user_id"] for m in members}

    success = []
    failed = []
    skipped = []

    for email in set(user_emails):
        try:
            user = api_manager_v2.get_user_by_email(email)
            if user["account_id"] in member_ids:
                skipped.append(email)
                continue

            api_manager_v2.add_user_to_org(
                user_id=user["account_id"], org_id=org_id, member_type="member"
            )
            success.append(email)
        except sheet_api_repo_v2.UserNotFoundError:
            failed.append(email)

    return {"success": success, "failed": failed, "skipped": skipped}


@router.delete("/organization/{org_id}")
async def delete_organization(org_id: str, user: CurrentUser):
    """
    Delete an organization.
    This will delete the organization, all its memberships and sheets.
    Only organization admins can delete an organization.

    Args:
        org_id: The ID of the organization to delete

    Returns:
        dict: Confirmation message
    """
    if not api_manager_v2.check_user_access_for_owner(
        user.sub, org_id
    ):  # TODO should be admin
        raise HTTPException("Not authorized to delete account.")

    deleted_items = api_manager_v2.delete_organization(org_id)
    return {"message": f"Delete success", "items": deleted_items}
