from datetime import datetime

import gspread
import randomname
from fastapi import HTTPException, status

from jedwal.account import service as account_service
from jedwal.account.models import AccountId
from jedwal.apis import google_sheets, repository
from jedwal.apis.models import Api, ApiCreate, ApiKey, ApiRead, ApiUpdate
from jedwal.apis.worksheets import service as worksheet_service
from jedwal.database.core import DbTable


def get_api(*, table: DbTable, owner_id: AccountId, api_id: ApiKey) -> Api | None:
    return repository.get_api(table=table, owner_id=owner_id, api_id=api_id)


def get_api_spreadsheet(*, api: Api) -> gspread.Spreadsheet:
    gspread_client = google_sheets.gspread_from_refresh_token_info(
        refresh_token_info=api.refresh_token_info
    )
    return google_sheets.open_spreadsheet(
        gspread_client=gspread_client, sheet_id=api.google_sheet_id
    )


def get_api_data(
    *, table: DbTable, api: Api, worksheet_name: str | None = None
) -> dict:
    """Get data from a sheet API with caching."""
    from jedwal.apis.worksheets import service as worksheet_service

    # If no worksheet specified, get the first sheet's name
    # and keep spreadsheet so that we can (optionally) pass it
    # along to get_worksheet_data to avoid double fetching
    spreadsheet = None
    if worksheet_name is None:
        spreadsheet = get_api_spreadsheet(api=api)
        worksheet_name = spreadsheet.sheet1.title

    data, expires_at = worksheet_service.get_worksheet_data(
        table=table, api=api, worksheet_name=worksheet_name, spreadsheet=spreadsheet
    )

    return {
        "title": worksheet_name,
        "sheet_id": api.google_sheet_id,
        "data": data,
        "expires_at": expires_at,
    }


def get_apis_for_account(*, table: DbTable, owner_id: AccountId) -> list[ApiRead]:
    """Get all APIs for an account with cached spreadsheet titles.

    Spreadsheet titles are cached on API creation and can be refreshed manually.
    Worksheet names can be fetched separately via the worksheets endpoint.
    """
    apis = repository.get_apis_by_owner(table=table, owner_id=owner_id)
    api_reads = []

    for api in apis:
        # TEMP: update spreadsheet_title if it's empty
        if api.spreadsheet_title is None:
            refresh_spreadsheet_title(
                table=table, owner_id=api.owner_id, api_id=api.api_key
            )

        api_reads.append(
            ApiRead(
                api_key=api.api_key,
                owner_id=api.owner_id,
                cache_duration=api.cache_duration,
                frozen=api.frozen,
                created_at=api.created_at,
                updated_at=api.updated_at,
                google_sheet_id=api.google_sheet_id,
                spreadsheet_title=api.spreadsheet_title,
            )
        )
    return api_reads


def create_api(*, table: DbTable, api_create: ApiCreate) -> Api:
    account = account_service.get_account(table=table, id=api_create.owner_id)
    free_account = account.account_status == "free"

    existing_apis = repository.get_apis_by_owner(
        table=table, owner_id=api_create.owner_id
    )
    if free_account and len(existing_apis) >= 2:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Free accounts can only have 2 sheet APIs.",
        ) from None

    google_sheet_id = _extract_sheet_id_from_url(api_create.google_sheet_id)

    existing_api = repository.get_api_by_google_sheet_id(
        table=table, owner_id=api_create.owner_id, google_sheet_id=google_sheet_id
    )
    if existing_api:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"API already exists for this Google Sheet: {existing_api.api_key}",
        ) from None

    gspread_client = google_sheets.gspread_from_refresh_token_info(
        refresh_token_info=api_create.refresh_token_info
    )

    try:
        spreadsheet = google_sheets.open_spreadsheet(
            gspread_client=gspread_client, sheet_id=google_sheet_id
        )
    except google_sheets.InaccessibleDocument as e:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid document type. Only Google Sheets are supported.",
        ) from e
    except google_sheets.InsufficientPermissions as e:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this Google Sheet. Please check your permissions in Google.",
        ) from e

    # Generate unique API key and create the API
    api_key = _generate_unique_api_key(table=table, owner_id=api_create.owner_id)
    now = datetime.now()

    api = Api(
        api_key=api_key,
        owner_id=api_create.owner_id,
        google_sheet_id=google_sheet_id,
        refresh_token_info=api_create.refresh_token_info,
        frozen=api_create.frozen,
        cache_duration=api_create.cache_duration,
        spreadsheet_title=spreadsheet.title,
        created_at=now,
        updated_at=now,
    )

    return repository.create_api(table=table, api=api)


def update_api(
    *, table: DbTable, owner_id: AccountId, api_id: ApiKey, updates: ApiUpdate
) -> Api:
    """Update an API. If cache_duration is changed, all worksheet caches are invalidated."""
    # Only update fields that were explicitly provided
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        return repository.get_api(table=table, owner_id=owner_id, api_id=api_id)

    # If cache_duration has changed, invalidate all worksheets
    if "cache_duration" in update_data:
        existing_api = repository.get_api(table=table, owner_id=owner_id, api_id=api_id)
        updated_cache_duration = update_data["cache_duration"]
        if existing_api and updated_cache_duration != existing_api.cache_duration:
            worksheet_service.delete_all_worksheets_for_api(
                table=table, owner_id=owner_id, api_key=api_id
            )

    return repository.update_api(
        table=table, owner_id=owner_id, api_id=api_id, updates=update_data
    )


def delete_api(*, table: DbTable, owner_id: AccountId, api_id: ApiKey):
    """
    Delete an API and all its associated worksheet caches.

    Args:
        table: DynamoDB table resource
        owner_id: Owner account ID
        api_id: API key to delete
    """
    worksheet_service.delete_all_worksheets_for_api(
        table=table, owner_id=owner_id, api_key=api_id
    )
    repository.delete_api(table=table, owner_id=owner_id, api_key=api_id)


def refresh_spreadsheet_title(
    *, table: DbTable, owner_id: AccountId, api_id: ApiKey
) -> Api:
    """
    Refresh the cached spreadsheet title from Google Sheets.

    Args:
        table: DynamoDB table resource
        owner_id: Owner account ID
        api_id: API key

    Returns:
        Updated Api with fresh spreadsheet title
    """
    api = get_api(table=table, owner_id=owner_id, api_id=api_id)
    spreadsheet = get_api_spreadsheet(api=api)

    return repository.update_api(
        table=table,
        owner_id=owner_id,
        api_id=api_id,
        updates={"spreadsheet_title": spreadsheet.title},
    )


def _generate_unique_api_key(*, table: DbTable, owner_id: AccountId) -> str:
    def key_exists(key: str) -> bool:
        api = repository.get_api(table=table, owner_id=owner_id, api_id=key)
        return api is not None

    name = randomname.get_name()
    while key_exists(name):
        name = randomname.get_name()

    return name


def _extract_sheet_id_from_url(google_id_or_url: str) -> str:
    if "docs.google.com/spreadsheets/d/" in google_id_or_url:
        return google_id_or_url.split("/d/")[1].split("/")[0]
    return google_id_or_url
