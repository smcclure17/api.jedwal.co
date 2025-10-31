from pydantic import EmailStr
from jedwal.account.models import Account, AccountRead
from jedwal.account import repository
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
