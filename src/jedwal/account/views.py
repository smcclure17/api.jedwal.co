from fastapi import APIRouter

from jedwal.account.models import AccountId, AccountRead
from jedwal.account.service import delete_account, get_account_or_organization_read
from jedwal.database.core import DbTable

account_router = APIRouter(tags=["accounts"])


@account_router.get("/", response_model=AccountRead)
async def get(account_id: AccountId, table: DbTable):
    """Get account details for the authenticated user."""
    return get_account_or_organization_read(table=table, id=account_id)


@account_router.delete("/", response_model=None)
async def delete_account_endpoint(account_id: AccountId, table: DbTable):
    """Delete the authenticated user's account."""
    return delete_account(table=table, id=account_id)
