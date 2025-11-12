from datetime import UTC, datetime, timedelta
from typing import Any

import gspread
from fastapi import HTTPException, status

from jedwal.apis import google_sheets
from jedwal.apis.models import Api
from jedwal.apis.repository import get_api
from jedwal.apis.worksheets import repository
from jedwal.apis.worksheets.models import WorksheetCreate
from jedwal.database.core import DbTable


def get_worksheet_model(*, table: DbTable, api: Api, worksheet_name: str):
    return repository.get_worksheet(
        table=table, owner_id=api.owner_id, api_key=api.api_key, title=worksheet_name
    )


def get_worksheet_data(
    *,
    table: DbTable,
    api: Api,
    worksheet_name: str,
    spreadsheet: gspread.Spreadsheet | None = None,
) -> tuple[list[dict[str, Any]], datetime]:
    """Get worksheet data. Uses cache if fresh, fetches from Google if expired/missing.

    Returns:
        tuple where first item is data, second item is expiration timestamp
    """
    from jedwal.apis.service import get_api_spreadsheet

    cached = repository.get_worksheet(
        table=table, owner_id=api.owner_id, api_key=api.api_key, title=worksheet_name
    )

    if cached and not cached.is_expired:
        return cached.data, cached.expires_at

    # Use provided spreadsheet or fetch new one
    if spreadsheet is None:
        spreadsheet = get_api_spreadsheet(api=api)

    try:
        ws = spreadsheet.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "Worksheet not found"}],
        ) from e

    try:
        data = google_sheets.read_worksheet(worksheet=ws)
    except google_sheets.NonUniqueColumnsError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=[{"msg": str(e)}]
        ) from e

    # update the worksheet for next time
    expires_at = datetime.now(UTC) + timedelta(seconds=api.cache_duration)
    repository.save_worksheet(
        table=table,
        worksheet_create=WorksheetCreate(
            owner_id=api.owner_id,
            api_key=api.api_key,
            title=worksheet_name,
            data=data,
            expires_at=expires_at,
        ),
    )

    return data, expires_at


# TODO: these next functions should maybe accept an API object instead,
# but the functions that use this don't have an API object at the moment,
# so it's easier/faster to just pass the keys.
def delete_all_worksheets_for_api(*, table: DbTable, owner_id: str, api_key: str):
    """Deletes all worksheets affiliated with an API"""
    return repository.delete_all_worksheets_for_api(
        table=table, owner_id=owner_id, api_key=api_key
    )


def get_google_worksheets_for_api(
    *, table: DbTable, owner_id: str, api_key: str
) -> list[gspread.Worksheet]:
    """Get all live worksheet objects from Google Sheets for an API.

    This fetches the complete, up-to-date list directly from Google Sheets.
    Returns gspread.Worksheet objects (which have .title property).
    """
    api = get_api(table=table, owner_id=owner_id, api_id=api_key)
    if api is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=[{"msg": "Api Not Found"}]
        ) from None
    gspread_client = google_sheets.gspread_from_refresh_token_info(
        refresh_token_info=api.refresh_token_info
    )
    spreadsheet = google_sheets.open_spreadsheet(
        gspread_client=gspread_client, sheet_id=api.google_sheet_id
    )
    return spreadsheet.worksheets()
