from pydantic import EmailStr

from jedwal.account import repository
from jedwal.account.models import Account, AccountRead
from jedwal.database.core import DbTable


def get_account(*, table: DbTable, id: str) -> Account:
    return repository.get_account(table=table, id=id)


def get_account_by_email(*, table: DbTable, email: EmailStr) -> Account:
    return repository.get_account_by_email(table=table, email=email)


def create_account(*, table: DbTable, account: Account):
    return repository.create_account(table=table, account=account)


def get_account_read(*, table: DbTable, id: str) -> AccountRead:
    account = repository.get_account(table=table, id=id)
    return AccountRead.from_account(account)


def delete_account(*, table: DbTable, id: str) -> None:
    from jedwal.apis.service import delete_api, get_apis_for_account
    account_apis = get_apis_for_account(table=table, owner_id=id)

    for account in account_apis:
        delete_api(table=table, owner_id=id, api_id=account.api_key)

    repository.delete_account(table=table, id=id)
