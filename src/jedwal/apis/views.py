from fastapi import APIRouter, BackgroundTasks, Response, status

from jedwal.apis import service
from jedwal.apis.models import (
    ApiCreate,
    ApiCreateRequest,
    ApiRead,
    ApiSpreadsheetDataRead,
    ApiUpdate,
)
from jedwal.apis.worksheets.views import authenticated_worksheets_router
from jedwal.auth.service import VerifiedAccount
from jedwal.database.core import DbTable

public_apis_router = APIRouter(prefix="/apis")
authenticated_apis_router = APIRouter(prefix="/apis")

# Include worksheets router as a sub-router of APIs
authenticated_apis_router.include_router(
    authenticated_worksheets_router, prefix="/{api_id}"
)


@public_apis_router.get("/{api_id}", response_model=ApiSpreadsheetDataRead)
async def get_api_data(
    account_id: str,
    api_id: str,
    table: DbTable,
    worksheet: str | None = None,
):
    """Get data from a sheet API endpoint."""
    api = service.get_api(table=table, owner_id=account_id, api_id=api_id)
    return service.get_api_data(table=table, api=api, worksheet_name=worksheet)


@authenticated_apis_router.get("", response_model=list[ApiRead])
async def get_apis_for_account(
    account_id: str,
    table: DbTable,
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
        spreadsheet_title=created_api.spreadsheet_title,
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

    # TODO: Invalidate CloudFront cache in background for api and it's worksheets

    return ApiRead(
        api_key=updated_api.api_key,
        owner_id=updated_api.owner_id,
        google_sheet_id=updated_api.google_sheet_id,
        frozen=updated_api.frozen,
        cache_duration=updated_api.cache_duration,
        spreadsheet_title=updated_api.spreadsheet_title,
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

    # TODO: invalidate cache in cloudfront for item and all worksheets


@authenticated_apis_router.post("/{api_id}/refresh-title", response_model=ApiRead)
async def refresh_spreadsheet_title(
    account_id: str,
    api_id: str,
    table: DbTable,
):
    """Manually refresh the spreadsheet title from Google Sheets."""
    updated_api = service.refresh_spreadsheet_title(
        table=table, owner_id=account_id, api_id=api_id
    )

    return ApiRead(
        api_key=updated_api.api_key,
        owner_id=updated_api.owner_id,
        google_sheet_id=updated_api.google_sheet_id,
        frozen=updated_api.frozen,
        cache_duration=updated_api.cache_duration,
        spreadsheet_title=updated_api.spreadsheet_title,
        created_at=updated_api.created_at,
        updated_at=updated_api.updated_at,
    )
