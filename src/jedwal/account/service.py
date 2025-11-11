from fastapi import HTTPException, status
from pydantic import EmailStr

from jedwal.account import repository
from jedwal.account.models import Account, AccountRead
from jedwal.common.email_templates import build_owner_alert_email, build_welcome_email
from jedwal.config import settings
from jedwal.database.core import DbTable
from jedwal.emails import service as email_service


def get_account(*, table: DbTable, id: str) -> Account | None:
    return repository.get_account(table=table, id=id)


# TODO: There's some tension here between organizations and accounts.
# Accounts and orgs are very similar in that they operate the same
# within the app (they can both create APIs, Posts, etc.), but there are
# metadata/management differences (Orgs have a billing account and no email etc.)
# On the frontend, we want both app.jedwal.co/account-id and /org-id to work the same
# so for now I'm just adding a general lookup here.
def get_account_or_organization_read(*, table: DbTable, id: str) -> AccountRead:
    account = repository.get_account_or_organization(table=table, id=id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=[{"msg": "Account not found"}]
        ) from None
    return AccountRead.from_account_or_org(account=account)


def get_account_by_email(*, table: DbTable, email: EmailStr) -> Account:
    return repository.get_account_by_email(table=table, email=email)


def create_account(*, table: DbTable, account: Account):
    account = repository.create_account(table=table, account=account)
    if settings.emails_enabled and not account.do_not_email:
        email_template = build_welcome_email(
            to_email=account.email,
            account_first_name=account.given_name,
            user_id=account.account_id,
        )
        email_service.send_email(table=table, email_data=email_template)
        owner_email = build_owner_alert_email(
            email=account.email,
            account_id=account.account_id,
            display_name=account.display_name,
        )
        email_service.send_email(table=table, email_data=owner_email)


def get_account_read(*, table: DbTable, id: str) -> AccountRead:
    account = repository.get_account(table=table, id=id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=[{"msg": "Account not found"}]
        ) from None
    return AccountRead.from_account(account)


def delete_account(*, table: DbTable, id: str) -> None:
    from jedwal.apis.service import delete_api, get_apis_for_account

    account = repository.get_account(table=table, id=id)
    if account is None:
        raise HTTPException(
            status_code=400,
            detail=[
                {
                    "msg": "Cannot delete organization from this endpoint. "
                    "Use /organizations/{org_id} instead."
                }
            ],
        ) from None

    account_apis = get_apis_for_account(table=table, owner_id=id)

    for account in account_apis:
        delete_api(table=table, owner_id=id, api_id=account.api_key)

    repository.delete_account(table=table, id=id)


def update_account(*, table: DbTable, account: Account):
    return repository.update_account(table=table, account=account)
