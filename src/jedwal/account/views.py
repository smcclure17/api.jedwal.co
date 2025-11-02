from fastapi import APIRouter

from jedwal.account.models import AccountRead
from jedwal.account.service import delete_account, get_account_read
from jedwal.database.core import DbTable

account_router = APIRouter()


@account_router.get("/", response_model=AccountRead)
async def get_account(account_id: str, table: DbTable):
    """Get account details for the authenticated user."""
    return get_account_read(table=table, id=account_id)


@account_router.delete("/", response_model=None)
async def delete_account_endpoint(account_id: str, table: DbTable):
    """Delete the authenticated user's account."""
    return delete_account(table=table, id=account_id)
