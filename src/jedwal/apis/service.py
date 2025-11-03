from datetime import datetime

import gspread
import randomname
from fastapi import HTTPException, status

from jedwal.account import service as account_service
from jedwal.apis import google_sheets, repository
from jedwal.apis.models import Api, ApiCreate, ApiRead, ApiUpdate
from jedwal.common.google_auth_fields import GoogleOauthFields
from jedwal.config.config import settings
from jedwal.database.core import DbTable


def get_api(*, table: DbTable, owner_id: str, api_id: str) -> Api:
    return repository.get_api(table=table, owner_id=owner_id, api_id=api_id)


def get_api_spreadsheet(
    *, table: DbTable, owner_id: str, api_id: str
) -> gspread.Spreadsheet:
    api = get_api(table=table, owner_id=owner_id, api_id=api_id)

    gspread_client = google_sheets.gspread_from_refresh_token_info(
        refresh_token_info=api.refresh_token_info
    )
    return google_sheets.open_spreadsheet(
        gspread_client=gspread_client, sheet_id=api.google_sheet_id
    )


def get_api_data(
    *, table: DbTable, owner_id: str, api_id: str, worksheet_name: str | None = None
) -> dict:
    """
    Get data from a sheet API.

    Args:
        table: DynamoDB table resource
        owner_id: Owner account ID
        api_id: API identifier
        worksheet_name: Optional worksheet name. If None, returns first sheet.

    Returns:
        Dict with spreadsheet title, id, and data
    """
    spreadsheet = get_api_spreadsheet(table=table, owner_id=owner_id, api_id=api_id)

    if worksheet_name:
        worksheet = spreadsheet.worksheet(worksheet_name)
    else:
        worksheet = spreadsheet.sheet1

    try:
        data = google_sheets.read_worksheet(worksheet=worksheet)
    except google_sheets.NonUniqueColumnsError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=[{"msg": str(e)}]
        )

    return {
        "title": spreadsheet.title,
        "sheet_id": spreadsheet.id,
        "data": data,
    }


def get_apis_for_account(*, table: DbTable, owner_id: str) -> list[ApiRead]:
    apis = repository.get_apis_by_owner(table=table, owner_id=owner_id)

    api_reads = []
    for api in apis:

        gspread_client = google_sheets.gspread_from_refresh_token_info(
            refresh_token_info=api.refresh_token_info
        )

        spreadsheet = google_sheets.open_spreadsheet(
            gspread_client=gspread_client, sheet_id=api.google_sheet_id
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
                worksheet_names=[ws.title for ws in spreadsheet.worksheets()],
            )
        )
    return api_reads


def create_api(*, table: DbTable, api_create: ApiCreate) -> tuple[Api, str]:

    account = account_service.get_account(table=table, id=api_create.owner_id)
    free_account = account.account_status == "free"

    existing_apis = repository.get_apis_by_owner(
        table=table, owner_id=api_create.owner_id
    )
    if free_account and len(existing_apis) >= 2:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Free accounts can only have 2 sheet APIs.",
        )

    google_sheet_id = _extract_sheet_id_from_url(api_create.google_sheet_id)

    existing_api = repository.get_api_by_google_sheet_id(
        table=table, owner_id=api_create.owner_id, google_sheet_id=google_sheet_id
    )
    if existing_api:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"API already exists for this Google Sheet: {existing_api.api_key}",
        )

    gspread_client = google_sheets.gspread_from_refresh_token_info(
        refresh_token_info=api_create.refresh_token_info
    )

    try:
        google_sheets.open_spreadsheet(
            gspread_client=gspread_client, sheet_id=google_sheet_id
        )
    except google_sheets.InaccessibleDocument:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid document type. Only Google Sheets are supported.",
        )
    except google_sheets.InsufficientPermissions:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this Google Sheet. Please check your permissions in Google.",
        )

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
        created_at=now,
        updated_at=now,
    )

    created_api = repository.create_api(table=table, api=api)
    url = f"{settings.api_base_url}/{api_create.owner_id}/api/{api_key}"
    return created_api, url


def update_api(
    *, table: DbTable, owner_id: str, api_id: str, updates: ApiUpdate
) -> Api:
    # Only update fields that were explicitly provided
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        # No fields to update, just return existing API
        return repository.get_api(table=table, owner_id=owner_id, api_id=api_id)

    return repository.update_api(
        table=table, owner_id=owner_id, api_id=api_id, updates=update_data
    )


def delete_api(*, table: DbTable, owner_id: str, api_id: str):
    repository.delete_api(table=table, owner_id=owner_id, api_key=api_id)


def _generate_unique_api_key(*, table: DbTable, owner_id: str) -> str:
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
