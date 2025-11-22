from datetime import UTC, datetime

from jedwal.account.models import AccountId
from jedwal.database.core import DbTable
from jedwal.organizations.membership import repository
from jedwal.organizations.membership.models import (
    Membership,
    MembershipCreate,
    MemberType,
)


def create_memberships(
    *, table: DbTable, memberships: list[Membership]
) -> list[Membership]:
    return repository.create_memberships(table=table, memberships=memberships)


def create_memberships_from_emails(
    *, table: DbTable, organization_id: str, memberships: list[MembershipCreate]
):
    from jedwal.account.service import get_account_by_email
    from jedwal.common.exceptions import NotFoundException

    validated_memberships = []
    for mem in memberships:
        try:
            account = get_account_by_email(table=table, email=mem.email)
            validated_memberships.append(
                Membership(
                    account_id=account.account_id,
                    joined_at=datetime.now(tz=UTC),
                    member_type=mem.member_type,
                    organization_id=organization_id,
                )
            )
        except NotFoundException:
            continue  # Just skip accounts that aren't found.
    return create_memberships(table=table, memberships=validated_memberships)


def delete_membership(
    *, table: DbTable, account_id: AccountId, organization_id: str
) -> None:
    return repository.delete_membership(
        table=table, account_id=account_id, organization_id=organization_id
    )


def get_membership(
    *, table: DbTable, account_id: AccountId, organization_id: str
) -> Membership | None:
    return repository.get_membership(
        table=table, account_id=account_id, organization_id=organization_id
    )


def get_memberships_for_org(
    *, table: DbTable, organization_id: str
) -> list[Membership]:
    return repository.get_memberships_for_org(
        table=table, organization_id=organization_id
    )


def get_memberships_for_account(
    *, table: DbTable, account_id: AccountId
) -> list[Membership]:
    return repository.get_memberships_for_account(table=table, account_id=account_id)


def check_account_membership(
    *, table: DbTable, account_id: AccountId, organization_id: str
) -> MemberType | None:
    membership = get_membership(
        table=table, account_id=account_id, organization_id=organization_id
    )
    return membership.member_type if membership else None


def is_account_owner(
    *, table: DbTable, account_id: AccountId, organization_id: str
) -> bool:
    membership = get_membership(
        table=table, account_id=account_id, organization_id=organization_id
    )
    return membership is not None and membership.member_type == "owner"
