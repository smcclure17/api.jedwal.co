"""
Sheet management routes and operations.
"""

from typing import List

import gspread
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse

from sheetsapi import (
    auth_utils,
    dynamodb_sheet_repo,
    google_sheet_client,
    organization_helpers,
    sheet_api_manager,
    user_helpers,
)
from sheetsapi import config, cloudfront_helpers
from sheetsapi.models.api_models import (
    SheetMetadataResponse,
    UpdateApiTtlRequest,
    UpdateApiTtlResponse,
)
from dependencies import CurrentUser

router = APIRouter(tags=["sheets"])
api_manager = sheet_api_manager.SheetManager()
cloudfront = cloudfront_helpers.create_cloudfront_client()


@router.get("/api/{name}")
async def read_sheet(name: str, worksheet: str = "Sheet1"):
    """
    Get data from a sheet API.

    Args:
        name: Name of the sheet API
        worksheet: Name of the worksheet to read (default: Sheet1)

    Returns:
        JSONResponse: The data from the sheet
    """
    try:
        data = api_manager.get_worksheet_data(name, worksheet)
        if data.get("frozen"):
            raise HTTPException(401, "API is frozen. Upgrade to premium to unfreeze")

        return JSONResponse(
            content=data["data"],
            headers={"Cache-Control": f"max-age={data['cdn_ttl']}, public"},
            status_code=200,
        )
    except gspread.exceptions.WorksheetNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet} not found. To specify a worksheet, use, e.g., ?worksheet=your_sheet_name.",
        )
    except dynamodb_sheet_repo.SheetNotFound:
        raise HTTPException(status_code=404, detail="Sheet API not found.")


@router.get("/get-user-sheets", response_model=List[SheetMetadataResponse])
async def get_user_sheets(user: CurrentUser):
    """
    Get all sheets owned by the current user (personal sheets only).

    Returns:
        List[SheetMetadataResponse]: List of sheet metadata
    """
    sheets = api_manager.get_sheet_apis_for_email(user.email)
    return [SheetMetadataResponse.from_sheet_metadata(sheet) for sheet in sheets]


@router.post("/create-api")
async def create_api(
    sheet_id: str = Form(...),
    org_id: str = Form(None),  # Optional organization ID
    user: CurrentUser = None,
):
    """
    Create a new API for a Google Sheet.

    Args:
        sheet_id: Google Sheet ID or URL
        org_id: Optional organization ID (for org-owned sheets)

    Returns:
        dict: API URL and name
    """
    user_fields = user_helpers.fetch_fields_for_user(
        user.email, ["refreshToken", "premium", "apiCount", "userId"]
    )

    # Check user premium status if creating a personal sheet
    if not org_id and not user_fields.premium and user_fields.apiCount >= 3:
        raise HTTPException(
            403, detail="Non-premium users may only create up to 3 personal APIs."
        )

    # Check organization membership if org_id is provided
    if org_id:
        if not organization_helpers.is_organization_member(org_id, user_fields.userId):
            raise HTTPException(
                status_code=403, detail="You are not a member of this organization."
            )
        # Organization membership verified

    refresh_token = (
        user.refresh_token if user.refresh_token else user_fields.refreshToken
    )

    auth_creds = auth_utils.GoogleOauthFields.from_tokens(
        access_token=user.access_token,
        refresh_token=refresh_token,
    )

    # Hack: parse the sheet ID from the URL if it's a Google Sheets URL
    if "docs.google.com/spreadsheets/d/" in sheet_id:
        sheet_id = sheet_id.split("/d/")[1].split("/")[0]

    try:
        # Pass org_id directly instead of source_org string
        name = api_manager.add_sheet_to_repository(
            auth_creds, sheet_id, user.email, org_id
        )
    except google_sheet_client.InaccessibleDocument:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Only Google Sheets are accepted (not, e.g, xlsx).",
        )

    return {
        "url": f"{config.Config.Constants.API_BASE_URL}/api/{name}",
        "api_name": name,
    }


@router.post("/update-api-ttl", response_model=UpdateApiTtlResponse)
async def update_ttl(
    data: UpdateApiTtlRequest,
    user: CurrentUser = None,
):
    """
    Update how long an API is cached for before being refreshed.

    Args:
        data: Request containing the API name and new TTL

    Returns:
        UpdateApiTtlResponse: Confirmation message
    """
    user_fields = user_helpers.fetch_fields_for_user(user.email, ["premium", "userId"])
    api = api_manager.get_sheet_api_info(data.name)

    # Additional validation for non-premium users
    if not user_fields.premium and data.cdn_ttl < 60:
        raise HTTPException(
            status_code=422,
            detail="Invalid refresh duration. Non-premium users must set a value of 60 seconds or greater.",
        )

    if api is None:
        raise HTTPException(
            500, f"API with name {data.name} does not exist and cannot be updated."
        )

    # Check authorization based on ownership type
    if api.is_org_sheet:
        if not organization_helpers.is_organization_member(
            api.org_id, user_fields.userId
        ):
            raise HTTPException(
                403,
                f"User with email {user.email} is not a member of the organization that owns this API",
            )
    else:
        if api.email != user.email:
            raise HTTPException(
                401,
                f"User with email {user.email} not authorized to update API {data.name}",
            )

    api_manager.update_sheet_api_ttl(data.name, data.cdn_ttl)
    return UpdateApiTtlResponse(
        message=f"TTL for API '{data.name}' successfully updated to {data.cdn_ttl} seconds."
    )


# TODO: DELETE method was having issues with credentials. The user was not
# being passed. This should be a DELETE method, but for now we use GET.
@router.get("/delete-api/{name}")
async def delete_api(name: str, user: CurrentUser = None):
    """
    Delete a sheet API.

    Args:
        name: Name of the API to delete

    Returns:
        None
    """
    user_fields = user_helpers.fetch_fields_for_user(user.email, ["userId"])
    api = api_manager.get_sheet_api_info(name)
    if api is None:
        raise HTTPException(
            404, f"API with name {name} does not exist and cannot be deleted."
        )

    # Check authorization based on ownership type
    if api.is_org_sheet:
        if not organization_helpers.is_organization_member(
            api.org_id, user_fields.userId
        ):
            raise HTTPException(
                403,
                f"User with email {user.email} is not a member of the organization that owns this API",
            )
    else:
        if api.email != user.email:
            raise HTTPException(
                401, f"User with email {user.email} not authorized to delete API {name}"
            )

    # User is authorized to delete this sheet
    api_manager.remove_sheet_from_repository(name, email=user.email)

    # Invalidate the cloudfront key for this sheet to make sure the API
    # is immediately inaccessible.
    if cloudfront is not None:
        cloudfront_helpers.invalidate_cache(
            cloudfront=cloudfront,
            distribution_id=config.Config.Constants.CLOUDFRONT_DISTRIBUTION_ID,
            path=f"/api/{name}",
        )
