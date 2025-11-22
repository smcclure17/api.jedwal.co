from fastapi import APIRouter

from jedwal.account.models import AccountId
from jedwal.apis.models import ApiKey
from jedwal.apis.worksheets import service
from jedwal.apis.worksheets.models import WorksheetNamesRead
from jedwal.database.core import DbTable

authenticated_worksheets_router = APIRouter(prefix="/worksheets")


@authenticated_worksheets_router.get("", response_model=WorksheetNamesRead)
async def get_worksheets_for_api(
    account_id: AccountId,
    api_id: ApiKey,
    table: DbTable,
):
    """Get all worksheet names for an API from cache.

    Returns only worksheets that have been accessed at least once.
    For a complete list including never-accessed sheets, fetch directly from Google.
    """
    worksheets = service.get_google_worksheets_for_api(
        table=table, owner_id=account_id, api_key=api_id
    )
    return {"worksheets": [worksheet.title for worksheet in worksheets]}
