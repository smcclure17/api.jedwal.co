from pydantic import EmailStr
from jedwal.account.models import Account
from jedwal.account import repository
from jedwal.database.core import get_table
from jedwal.config import settings


def get_account(*, id: str) -> Account:
    table = get_table(settings.sheets_api_table)  # TODO: better DI
    return repository.get_account(table=table, id=id)


def get_account_by_email(*, email: EmailStr) -> Account:
    table = get_table(settings.sheets_api_table)  # TODO: better DI
    return repository.get_account_by_email(table=table, email=email)


def create_account(*, account: Account):
    table = get_table(settings.sheets_api_table)  # TODO: better DI
    return repository.create_account(table=table, account=account)
