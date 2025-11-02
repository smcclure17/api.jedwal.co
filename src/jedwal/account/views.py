from fastapi import APIRouter, HTTPException, status

from jedwal.account.models import AccountRead
from jedwal.account.service import get_account_read
from jedwal.auth.service import CurrentAccount, has_required_permissions
from jedwal.database.core import DbTable

account_router = APIRouter()


@account_router.get("/", response_model=AccountRead)
async def get_account(account_id: str, table: DbTable, current_account: CurrentAccount):
    if not has_required_permissions(
        current_account=current_account, account_id=account_id
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unauthorized"
        )

    return get_account_read(table=table, id=account_id)
