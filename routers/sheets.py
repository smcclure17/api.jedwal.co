"""
Sheet management routes and operations.
"""

from typing import Annotated
import gspread
from fastapi import APIRouter, Body, Form, HTTPException
from fastapi.responses import JSONResponse

from sheetsapi import google_sheet_client, lru_cache
from sheetsapi import config, cloudfront_helpers
from sheetsapi.models.api_models import (
    GetAllSheetsResponse,
    SheetMetadata,
    SheetMetadataFailure,
    UpdateApiTtlRequest,
    UpdateApiTtlResponse,
)
from dependencies import CurrentUser
from sheetsapi.sheet_repo import SheetApiNotFoundError, SheetApiRepo
from sheetsapi.account_repo import AccountRepo

router = APIRouter(tags=["sheets"])
cloudfront = cloudfront_helpers.create_cloudfront_client()

sheet_repo = SheetApiRepo.from_table_name()
account_repo = AccountRepo.from_table_name()
lru_worksheet_cache = lru_cache.LRUCache(capacity=100)


@router.get("/api/{owner_id}/{sheet_api_name}")
async def read_sheet_v2(owner_id: str, sheet_api_name: str, worksheet: str = "Sheet1"):
    try:
        sheet_api = sheet_repo.get_api_metadata(owner_id, sheet_api_name)
    except SheetApiNotFoundError:
        raise HTTPException(404, detail="Sheet API not found.")

    google_sheet_id = sheet_api["google_sheet_id"]
    refresh_token_info = sheet_api["refresh_token_info"]
    cache_duration = sheet_api["cache_duration"]

    if sheet_api.get("frozen"):
        raise HTTPException(401, "API is frozen. Re-upgrade to premium to unfreeze")

    try:
        # Check cache for worksheet
        ws_cache_key = f"{owner_id}-{sheet_api_name}-{worksheet}"
        cached_worksheet = lru_worksheet_cache.get(ws_cache_key)
        if cached_worksheet is not None:
            worksheet = cached_worksheet
        else:
            google_client = google_sheet_client.GoogleSheets.from_token_info(
                refresh_token_info
            )
            worksheet = google_client.get_worksheet_by_name(google_sheet_id, worksheet)

        # Add worksheet to cache
        lru_worksheet_cache.put(ws_cache_key, value=worksheet)
        return JSONResponse(
            content=google_sheet_client.GoogleSheets.get_worksheet_data(worksheet),
            headers={"Cache-Control": f"max-age={cache_duration}, public"},
            status_code=200,
        )
    except gspread.exceptions.WorksheetNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet} not found. To specify a worksheet, use, e.g., ?worksheet=your_sheet_name.",
        )
    except SheetApiNotFoundError:
        raise HTTPException(status_code=404, detail="Sheet API not found.")
    except google_sheet_client.NonUniqueColumnsError:
        raise HTTPException(
            400,
            detail="Worksheet columns are not unique. Please check your column names.",
        )


@router.get("/get-all-sheets/{owner_id}", response_model=GetAllSheetsResponse)
async def get_sheets_metadata_v2(owner_id: str, user: CurrentUser):
    """Get all sheets owned by the current user (personal sheets only)."""
    if not account_repo.check_user_access_for_owner(user.sub, owner_id):
        raise HTTPException(403, "Not authorized")

    sheet_apis = sheet_repo.get_apis_for_account(owner_id)

    # Add worksheets
    results = []
    failures = []
    for sheet_api in sheet_apis:
        refresh_token_info = sheet_api["refresh_token_info"]
        google_sheet_id = sheet_api["google_sheet_id"]
        google_client = google_sheet_client.GoogleSheets.from_token_info(
            info=refresh_token_info
        )
        try:
            google_sheet_data = google_client.get_spreadsheet_data(google_sheet_id)
            results.append(SheetMetadata.from_temp_dicts(sheet_api, google_sheet_data))
        except google_sheet_client.InsufficientPermissions:
            failures.append(
                SheetMetadataFailure(
                    google_sheet_id=google_sheet_id,
                    hint="You don't have access to this Google Sheet, please check your permissions in Google.",
                    sheet_api_name=sheet_api["sheet_api_name"],
                )
            )
    return GetAllSheetsResponse(results=results, failures=failures)


@router.post("/api")
async def create_api_v2(
    google_id: Annotated[str, Body(...)],
    user: CurrentUser,
    owner_id: Annotated[str | None, Body(...)] = None,
):
    if owner_id is None:
        owner_id = user.sub  # fallback to use the user_id if no owner given
    else:
        if not account_repo.check_user_access_for_owner(user.sub, owner_id=owner_id):
            raise HTTPException(403, detail="Not authorized for organization.")

    # We use the user auth creds even if it's an organization sheet api
    user_item = account_repo.get_account(user.sub)
    refresh_token_info = user_item["refresh_token_info"]
    free_account = user_item["account_status"] == "free"
    number_of_apis = len(sheet_repo.get_apis_for_account(owner_id=owner_id))

    # check that user is premium or has less than 2 APIs
    if free_account and number_of_apis >= 2:
        raise HTTPException(401, detail="Free accounts can only have 2 sheet APIs.")

    # Hack: parse the sheet ID from the URL if it's a Google Sheets URL
    if "docs.google.com/spreadsheets/d/" in google_id:
        google_id = google_id.split("/d/")[1].split("/")[0]

    # Check the user has access to the Google Sheet
    google_client = google_sheet_client.GoogleSheets.from_token_info(refresh_token_info)
    try:
        google_client.get_spreadsheet_data(google_id)
    except google_sheet_client.InaccessibleDocument:
        raise HTTPException(
            415, detail="Invalid document type. Only Google Sheets are supported."
        )
    except google_sheet_client.InsufficientPermissions:
        raise HTTPException(
            415,
            detail="You don't have access to this Google Sheet, please check your permissions in Google.",
        )

    sheet_api_res = sheet_repo.create_api(
        owner_id=owner_id,
        google_sheet_id=google_id,
        refresh_token_info=refresh_token_info,
    )

    sheet_api_name = sheet_api_res["sheet_api_name"]
    return {
        "url": f"{config.Config.Constants.API_BASE_URL}/api/{owner_id}/{sheet_api_name}",
        "api_name": sheet_api_name,
    }


@router.delete("/delete-api/{owner_id}/{sheet_api_name}")
async def delete_api_v2(owner_id: str, sheet_api_name: str, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, owner_id):
        raise HTTPException(403, "Not authorized")

    # TODO: need to be either the user or an org admin to delete

    deleted_items = sheet_repo.delete_api(owner_id, sheet_api_name)

    if cloudfront is not None:
        cloudfront_helpers.invalidate_cache(
            cloudfront=cloudfront,
            distribution_id=config.Config.Constants.CLOUDFRONT_DISTRIBUTION_ID,
            path=f"/api/{owner_id}/{sheet_api_name}*",
        )
    return deleted_items


@router.post("/update-cache-duration", response_model=UpdateApiTtlResponse)
async def update_cache_duration_v2(data: UpdateApiTtlRequest, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, data.owner_id):
        raise HTTPException(403, "Not authorized")

    try:
        sheet_repo.update_api(
            owner_id=data.owner_id,
            sheet_api_name=data.api_name,
            fields={"cache_duration": data.cache_duration},
        )

        # Invalidate anything in the cache to ensure the TTL is updated right away.
        # Otherwise the TTL would not update until the old entry expires (could be days)
        if cloudfront is not None:
            cloudfront_helpers.invalidate_cache(
                cloudfront=cloudfront,
                distribution_id=config.Config.Constants.CLOUDFRONT_DISTRIBUTION_ID,
                path=f"/api/{data.owner_id}/{data.sheet_api_name}*",
            )

        return UpdateApiTtlResponse(message="Success!")
    except SheetApiNotFoundError:
        raise HTTPException(404, "Sheet API Not Found. Cannot modify cache duration")
