from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from jedwal.config import settings
from jedwal.database.core import DbTable
from jedwal.emails import service

public_email_router = APIRouter(prefix="/email", tags=["email"])


@public_email_router.get("/unsubscribe")
async def unsubscribe(table: DbTable, account_id: str = Query(...)):
    try:
        service.unsubscribe_user(table=table, user_id=account_id)
    except Exception:
        return RedirectResponse(url=f"{settings.client_base_url}/unsubscribe-error")
    return RedirectResponse(url=f"{settings.client_base_url}/unsubscribe-success")
