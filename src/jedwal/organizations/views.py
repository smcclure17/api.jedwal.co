from fastapi import APIRouter, Depends, status

from jedwal.account.models import AccountId
from jedwal.auth.service import verify_user_account
from jedwal.common.exceptions import NotFoundException
from jedwal.database.core import DbTable
from jedwal.organizations import service
from jedwal.organizations.membership.views import authenticated_memberships_router
from jedwal.organizations.models import (
    Organization,
    OrganizationCreateRequest,
)

authenticated_organization_router = APIRouter(
    prefix="/organizations",
    dependencies=[Depends(verify_user_account)],
    tags=["organizations"],
)

# Include worksheets router as a sub-router of APIs
authenticated_organization_router.include_router(
    authenticated_memberships_router,
    prefix="/{org_id}",  # account here means org
)


@authenticated_organization_router.get("", response_model=list[Organization])
async def get_organizations(account_id: AccountId, table: DbTable):
    """Get all memberships for an org/account."""
    orgs = service.get_organizations_for_account(table=table, account_id=account_id)
    return orgs


@authenticated_organization_router.get("/{org_id}", response_model=Organization)
async def get_organization(account_id: AccountId, org_id: str, table: DbTable):
    """Get all memberships for an org/account."""
    org = service.get_organization(table=table, organization_id=org_id)
    if org is None:
        raise NotFoundException
    return org


@authenticated_organization_router.head("/{org_id}")
async def head_organization(account_id: AccountId, org_id: str, table: DbTable):
    """Get all memberships for an org/account."""
    org = service.get_organization(table=table, organization_id=org_id)
    if org is None:
        raise NotFoundException


@authenticated_organization_router.post(
    "", response_model=None, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    account_id: AccountId,
    request: OrganizationCreateRequest,
    table: DbTable,
):
    service.create_organization(
        table=table,
        owner_account_id=account_id,
        organization_name=request.organization_name,
        membership_emails=request.memberships,
    )


@authenticated_organization_router.delete("/{org_id}", response_model=None)
async def delete_organization(
    account_id: AccountId,
    org_id: str,
    table: DbTable,
):
    return service.delete_organization(
        table=table, account_id=account_id, organization_id=org_id
    )
