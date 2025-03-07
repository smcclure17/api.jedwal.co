"""Organization management routes and operations."""

from typing import List
import logging

from fastapi import APIRouter, Body, Depends, Form, HTTPException
from pydantic import EmailStr

from sheetsapi import organization_helpers, sheet_api_manager, user_helpers
from sheetsapi.models.api_models import (
    CreateOrganizationRequest,
    OrganizationInviteMembersRequest,
    OrganizationMemberResponse,
    OrganizationMembersResponse,
    OrganizationResponse,
    SheetMetadataResponse,
)
from dependencies import CurrentUser, OrgMember

logger = logging.getLogger(__name__)

router = APIRouter(tags=["organizations"])
api_manager = sheet_api_manager.SheetManager()


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
    user_fields = user_helpers.fetch_fields_for_user(
        user.email, ["PK", "SK", "userId", "email", "premium"]
    )

    if not user_fields.premium:
        raise HTTPException(401, detail="Only premium members can create orgs.")

    org = organization_helpers.create_organization(data.name, user_fields)

    for email in data.invitees:
        if email == user.email:
            continue  # already added as admin
        try:
            user_id = user_helpers.lookup_user_id_by_email(email)
            organization_helpers.add_user_to_organization(
                org_id=org.orgId, email=email, user_id=user_id
            )
        except user_helpers.UserNotFound:
            logger.warning(f"User ${email} not found. Cannot add to org {org.orgId}")

    return OrganizationResponse(
        id=org.orgId, name=org.name, created_at=org.createdAt, created_by=org.createdBy
    )


@router.get("/organizations", response_model=List[OrganizationResponse])
async def get_user_organizations(user: CurrentUser):
    """
    Get all organizations the current user is a member of.

    Returns:
        List[OrganizationResponse]: List of organizations
    """
    user_id = user_helpers.lookup_user_id_by_email(user.email)
    memberships = organization_helpers.get_user_organizations(user_id)

    # For each membership, get the organization details
    organizations = []
    for membership in memberships:
        org = organization_helpers.get_organization(membership.orgId)
        if org:
            organizations.append(
                OrganizationResponse(
                    id=org.orgId,
                    name=org.name,
                    created_at=org.createdAt,
                    created_by=org.createdBy,
                )
            )

    return organizations


@router.get("/organization/{org_id}", response_model=OrganizationMembersResponse)
async def get_organization_details(org_id: str, _: OrgMember):
    """
    Get details about an organization, including its members.

    Args:
        org_id: The ID of the organization

    Returns:
        OrganizationMembersResponse: Organization details with member list
    """
    org = organization_helpers.get_organization(org_id)
    members = organization_helpers.get_organization_members(org_id)

    org_response = OrganizationResponse(
        id=org.orgId, name=org.name, created_at=org.createdAt, created_by=org.createdBy
    )

    member_responses = [
        OrganizationMemberResponse(
            user_id=member.userId,
            email=member.email,
            role=member.role,
            joined_at=member.joinedAt,
        )
        for member in members
    ]

    return OrganizationMembersResponse(
        organization=org_response, members=member_responses
    )


# HACK:  we need org_id in the params (not body) in order
# to use the OrgMember middleware/dependency.
@router.post("/organization/invite/{org_id}")
async def invite_user_to_organization(
    org_id, data: OrganizationInviteMembersRequest, _: OrgMember
):
    """
    Invite a user to an organization.

    Args:
        org_id: The ID of the organization
        email: The email of the user to invite

    Returns:
        dict: Confirmation message
    """
    members = organization_helpers.get_organization_members(org_id=org_id)
    member_emails = {member.email for member in members}

    successes = []
    failures = []
    skipped = []
    for email in set(data.emails):
        if email in member_emails:
            skipped.append(email)
            continue   # skip people who are already members
        try:
            invite_user_id = user_helpers.lookup_user_id_by_email(email)
            organization_helpers.add_user_to_organization(
                org_id=org_id, email=email, user_id=invite_user_id, role="member"
            )
            successes.append(email)
        except user_helpers.UserNotFound:
            failures.append(email)

    return {"successes": successes, "failures": failures, "skipped": skipped}


@router.delete("/organization/{org_id}")
async def delete_organization(
    org_id: str,
    user_id: OrgMember,
):
    """
    Delete an organization.
    This will delete the organization, all its memberships and sheets.
    Only organization admins can delete an organization.

    Args:
        org_id: The ID of the organization to delete

    Returns:
        dict: Confirmation message
    """
    try:
        organization_helpers.delete_organization(org_id, user_id)
        return {"message": f"Organization with ID {org_id} has been deleted."}
    except organization_helpers.NotOrganizationMember as e:
        raise HTTPException(status_code=403, detail=str(e))  # not admin


@router.get(
    "/get-organization-sheets/{org_id}", response_model=List[SheetMetadataResponse]
)
async def get_organization_sheets(org_id: str, _: OrgMember):
    """
    Get all sheets owned by an organization.

    Args:
        org_id: The ID of the organization

    Returns:
        List[SheetMetadataResponse]: List of sheet metadata
    """
    sheets = api_manager.get_sheet_apis_for_org(org_id)
    return [SheetMetadataResponse.from_sheet_metadata(sheet) for sheet in sheets]
