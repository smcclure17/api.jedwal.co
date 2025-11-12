from fastapi import APIRouter, status

from jedwal.database.core import DbTable
from jedwal.organizations.membership import service
from jedwal.organizations.membership.models import (
    MembershipCreateRequest,
    MembershipRead,
)

authenticated_memberships_router = APIRouter(prefix="/memberships")


@authenticated_memberships_router.get("", response_model=list[MembershipRead])
async def get_memberships_for_organization(
    org_id: str,
    table: DbTable,
):
    """Get all memberships for an org/account."""
    return service.get_memberships_for_org(table=table, organization_id=org_id)


@authenticated_memberships_router.post(
    "", response_model=list[MembershipRead], status_code=status.HTTP_201_CREATED
)
async def create_memberships(
    org_id: str,
    request: MembershipCreateRequest,
    table: DbTable,
):
    return service.create_memberships_from_emails(
        table=table, memberships=request.memberships, organization_id=org_id
    )
