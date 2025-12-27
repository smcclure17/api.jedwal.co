import re
from datetime import UTC, datetime

from jedwal.entitlements import service as entitlements_service
from jedwal.account import service as account_service
from jedwal.account.models import Account, AccountId
from jedwal.common.exceptions import ConflictException
from jedwal.database.core import DbTable
from jedwal.organizations import repository
from jedwal.organizations.membership import service as membership_service
from jedwal.organizations.membership.models import Membership, MembershipCreate
from jedwal.organizations.models import Organization


def get_organization(*, table: DbTable, organization_id: str) -> Organization | None:
    return repository.get_organization(table=table, id=organization_id)


def get_accounts_for_organization(
    *, table: DbTable, organization_id: str
) -> list[Account]:
    memberships = membership_service.get_memberships_for_org(
        table=table, organization_id=organization_id
    )

    accounts = []
    for membership in memberships:
        account = account_service.get_account(table=table, id=membership.account_id)
        if account is not None:
            accounts.append(account)

    return accounts


def get_organizations_for_account(
    *, table: DbTable, account_id: AccountId
) -> list[Organization]:
    """Get all organizations that an account is a member of."""
    memberships = membership_service.get_memberships_for_account(
        table=table, account_id=account_id
    )

    organizations = []
    for membership in memberships:
        org = repository.get_organization(table=table, id=membership.organization_id)
        if org is not None:
            organizations.append(org)

    return organizations


def create_organization(
    *,
    table: DbTable,
    owner_account_id: AccountId,
    organization_name: str,
    membership_emails: list[str] | None = None,
):
    owner_account = account_service.get_account(table=table, id=owner_account_id)
    entitlements_service.check_can_create_organization(account=owner_account)

    if membership_emails is None:
        member_memberships = []

    org_id = re.sub(r"\s+", "-", organization_name).lower()
    org = Organization(
        account_id=org_id,
        billing_account_id=owner_account_id,
        display_name=organization_name,
        account_status="premium",
    )

    try:
        created_org = repository.create_organization(table=table, org=org)
        try:
            owner_membership = Membership(
                account_id=owner_account_id,
                organization_id=org_id,
                member_type="owner",
                joined_at=datetime.now(UTC),
            )

            created_memberships = membership_service.create_memberships(
                table=table, memberships=[owner_membership]
            )

            if membership_emails:
                member_memberships = [
                    MembershipCreate(member_type="member", email=email)
                    for email in membership_emails
                ]
                additional_memberships = (
                    membership_service.create_memberships_from_emails(
                        table=table,
                        organization_id=org_id,
                        memberships=member_memberships,
                    )
                )
                created_memberships.extend(additional_memberships)

            return created_org, created_memberships

        except Exception:
            repository.delete_organization(table=table, account_id=org_id)
            raise
    except ConflictException as e:
        raise ConflictException(
            detail="Organization with this name already exists",
        ) from e


def delete_organization(*, table: DbTable, organization_id: str, account_id: AccountId):
    member_type = membership_service.check_account_membership(
        table=table, organization_id=organization_id, account_id=account_id
    )
    entitlements_service.check_can_delete_organization(member_status=member_type)

    memberships = membership_service.get_memberships_for_org(
        table=table, organization_id=organization_id
    )
    for mem in memberships:
        membership_service.delete_membership(
            table=table, organization_id=organization_id, account_id=mem.account_id
        )
    repository.delete_organization(table=table, account_id=organization_id)
