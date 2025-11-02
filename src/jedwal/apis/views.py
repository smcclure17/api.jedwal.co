from fastapi import APIRouter, status

from jedwal.apis import service
from jedwal.apis.models import (
    ApiCreate,
    ApiCreateRequest,
    ApiRead,
    ApiSpreadsheetDataRead,
    ApiUpdate,
)
from jedwal.auth.service import VerifiedAccount
from jedwal.database.core import DbTable

public_apis_router = APIRouter(prefix="/api")
authenticated_apis_router = APIRouter(prefix="/apis")


@public_apis_router.get("/{api_id}", response_model=ApiSpreadsheetDataRead)
async def get_api_data(
    account_id: str,
    api_id: str,
    table: DbTable,
    worksheet: str | None = None,
):
    """Get data from a sheet API endpoint."""
    return service.get_api_data(
        table=table,
        owner_id=account_id,
        api_id=api_id,
        worksheet_name=worksheet,
    )


@authenticated_apis_router.get("", response_model=list[ApiRead])
async def get_apis_for_account(
    account_id: str,
    table: DbTable,
    worksheet: str | None = None,
):
    """Get all APIs for an account."""
    return service.get_apis_for_account(
        table=table,
        owner_id=account_id,
    )


@authenticated_apis_router.post(
    "", response_model=ApiRead, status_code=status.HTTP_201_CREATED
)
async def create_api(
    account_id: str,
    request: ApiCreateRequest,
    table: DbTable,
    verified_account: VerifiedAccount,
):
    """Create a new API endpoint for a Google Sheet.

    The account_id from the path determines the owner of the API.
    User must have permissions to manage this account (self or org).
    """
    # Build internal ApiCreate with refresh token from authenticated user
    api_create = ApiCreate(
        owner_id=account_id,  # Owner comes from path, not request body
        google_sheet_id=request.google_sheet_id,
        cache_duration=request.cache_duration,
        frozen=request.frozen,
        refresh_token_info=verified_account.refresh_token_info,
    )

    created_api, url = service.create_api(table=table, api_create=api_create)

    return ApiRead(
        api_key=created_api.api_key,
        owner_id=created_api.owner_id,
        google_sheet_id=created_api.google_sheet_id,
        frozen=created_api.frozen,
        cache_duration=created_api.cache_duration,
        created_at=created_api.created_at,
        updated_at=created_api.updated_at,
    )


@authenticated_apis_router.patch("/{api_id}", response_model=ApiRead)
async def update_api(
    account_id: str,
    api_id: str,
    updates: ApiUpdate,
    table: DbTable,
):
    """Update an API with partial updates."""
    updated_api = service.update_api(
        table=table,
        owner_id=account_id,
        api_id=api_id,
        updates=updates,
    )

    return ApiRead(
        api_key=updated_api.api_key,
        owner_id=updated_api.owner_id,
        google_sheet_id=updated_api.google_sheet_id,
        frozen=updated_api.frozen,
        cache_duration=updated_api.cache_duration,
        created_at=updated_api.created_at,
        updated_at=updated_api.updated_at,
    )


@authenticated_apis_router.delete("/{api_id}", response_model=None)
async def delete_api(
    account_id: str,
    api_id: str,
    table: DbTable,
):
    """Delete an API endpoint."""
    service.delete_api(table=table, owner_id=account_id, api_id=api_id)
