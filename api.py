import logging
import re
from typing import List

import fastapi
import gspread
import mangum
import stripe
from fastapi.responses import JSONResponse
from pydantic import EmailStr
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, Path

from sheetsapi import config, dynamodb_sheet_repo
from sheetsapi.models.api_models import (
    CreateOrganizationRequest,
    OrganizationMemberResponse,
    OrganizationMembersResponse,
    OrganizationResponse,
    SheetMetadataResponse,
    UpdateApiTtlRequest,
    UpdateApiTtlResponse,
    UserDataResponse,
)
from sheetsapi.models.domain_models import UserSession

logger = logging.getLogger(__name__)

# Initialize config first
config.Config.init()

# Then import modules that depend on config
from sheetsapi import (
    analytics_client,
    auth_utils,
    cloudfront_helpers,
    google_sheet_client,
    organization_helpers,
    sentry_helpers,
    sheet_api_manager,
    stripe_helpers,
    user_helpers,
)

sentry_helpers.init()

oauth = OAuth(config.Config.to_starlette_config())
analytics_handler = analytics_client.AnalyticsClient()
cloudfront = cloudfront_helpers.create_cloudfront_client()
api_manager = sheet_api_manager.SheetManager()

app = fastapi.FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=config.Config.Constants.OAUTH_SECRET_TOKEN,
    same_site="none",
    https_only=True,
    domain="jedwal.co",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        config.Config.Constants.CLIENT_BASE_URL,
        config.Config.Constants.CLIENT_APP_BASE_URL,
        config.Config.Constants.API_BASE_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "openid",
    "profile",
    "email",
]

OATH_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

oauth.register(
    name="google",
    server_metadata_url=OATH_METADATA_URL,
    client_kwargs={"scope": " ".join(OAUTH_SCOPES)},
)


def get_current_user(request: Request) -> UserSession:
    """Authentication middleware/dependency"""
    user = request.session.get("user")

    if user is None:
        raise fastapi.HTTPException(status_code=401, detail="Not authenticated")

    # TEMP: get access_token from session the old way
    if "access_token" not in user:
        user["access_token"] = request.session.get("access_token")
    return UserSession(**user)


def check_if_org_member(org_id: str, user: UserSession = Depends(get_current_user)):
    """Dependency to ensures the current user is a member of the specified organization."""
    user_fields = user_helpers.fetch_fields_for_user(user.email, ["userId"])
    org = organization_helpers.get_organization(org_id)
    if not org:
        raise fastapi.HTTPException(
            status_code=404, detail=f"Organization with ID {org_id} not found."
        )
    if not organization_helpers.is_organization_member(org_id, user_fields.userId):
        raise fastapi.HTTPException(
            status_code=403, detail="You are not a member of this organization."
        )
    return user_fields.userId


@app.get("/")
async def homepage(request: Request):
    user: dict | None = request.session.get("user")
    if user is not None:
        sheets = api_manager.get_sheet_apis_for_email(user["email"])
        html = f"""
        <style>
            body {{
                font-family: sans-serif;
            }}
        </style>
        <h1>Google Sheets API</h1>
        <h2>Hello, {user.get("given_name")}!</h2>
        <form action="/create-api" method="post">
            <input type="text" name="sheet_id" placeholder="Enter Google Sheet ID" style="width: 400px;">
            <button type="submit">Create API</button>
        </form>
        <h3>Your Sheets:</h3>
        <ul class="sheet-list">
            {_generate_sheet_list_items(sheets)}
        </ul>
        <a href="/logout">logout</a>
        """

        return HTMLResponse(html)
    return HTMLResponse(
        '<a href="/login" style="font-family: sans-serif;">please login</a>'
    )


@app.get("/login")
async def login(request: Request):
    redirect_uri = f"{config.Config.Constants.API_BASE_URL}/auth"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline"
    )


@app.get("/auth")
async def auth(request: Request):
    try:
        token: dict = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        request.session.pop("user", None)
        logger.error(f"Error: {e.error}")
        raise fastapi.HTTPException(
            status_code=500, detail=f"Something went wrong {e.error}"
        )
    user_token = token.get("userinfo")
    if user_token:
        user = UserSession(
            **user_token,
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
        )
        request.session["user"] = user.model_dump()

    user_helpers.persist_user_if_not_exists(user)
    return RedirectResponse(url=config.Config.Constants.CLIENT_APP_BASE_URL)


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    request.session.pop("refresh_token", None)
    return RedirectResponse(url=config.Config.Constants.CLIENT_BASE_URL)


@app.get("/get-user-data", response_model=UserDataResponse)
async def get_user_data(user: UserSession = Depends(get_current_user)):
    user_fields = user_helpers.fetch_fields_for_user(
        user.email, fields=["apiCount", "premium", "userId"]
    )

    if user_fields is None:
        raise ValueError(f"No fields found for user {user.email}")

    return UserDataResponse(
        id=user_fields.userId,
        email=user.email,
        name=user.name,
        api_count=user_fields.apiCount,
        premium=user_fields.premium,
    )


@app.get("/api/{name}")
async def read_sheet(name: str, worksheet: str = "Sheet1"):
    try:
        data = api_manager.get_worksheet_data(name, worksheet)
        if data.get("frozen"):
            raise fastapi.HTTPException(
                401, "API is frozen. Upgrade to premium to unfreeze"
            )

        return JSONResponse(
            content=data["data"],
            headers={"Cache-Control": f"max-age={data['cdn_ttl']}, public"},
            status_code=200,
        )
    except gspread.exceptions.WorksheetNotFound:
        raise fastapi.HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet} not found. To specify a worksheet, use, e.g., ?worksheet=your_sheet_name.",
        )
    except dynamodb_sheet_repo.SheetNotFound:
        raise fastapi.HTTPException(status_code=404, detail="Sheet API not found.")


@app.get("/get-user-sheets", response_model=list[SheetMetadataResponse])
async def get_user_sheets(user: UserSession = Depends(get_current_user)):
    """Get all sheets owned by the current user (personal sheets only)"""
    sheets = api_manager.get_sheet_apis_for_email(user.email)
    return [SheetMetadataResponse.from_sheet_metadata(sheet) for sheet in sheets]


@app.get(
    "/get-organization-sheets/{org_id}", response_model=list[SheetMetadataResponse]
)
async def get_organization_sheets(org_id: str, _=Depends(check_if_org_member)):
    """Get all sheets owned by an organization"""
    sheets = api_manager.get_sheet_apis_for_org(org_id)
    return [SheetMetadataResponse.from_sheet_metadata(sheet) for sheet in sheets]


@app.post("/create-api")
async def create_api(
    sheet_id: str = fastapi.Form(...),
    org_id: str = fastapi.Form(None),  # Optional organization ID
    user: UserSession = Depends(get_current_user),
):
    user_fields = user_helpers.fetch_fields_for_user(
        user.email, ["refreshToken", "premium", "apiCount", "userId"]
    )

    # Check user premium status if creating a personal sheet
    if not org_id and not user_fields.premium and user_fields.apiCount >= 3:
        raise fastapi.HTTPException(
            403, detail="Non-premium users may only create up to 3 personal APIs."
        )

    # Check organization membership if org_id is provided
    if org_id:
        if not organization_helpers.is_organization_member(org_id, user_fields.userId):
            raise fastapi.HTTPException(
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
        raise fastapi.HTTPException(
            status_code=415,
            detail="Unsupported file type. Only Google Sheets are accepted (not, e.g, xlsx).",
        )

    return {
        "url": f"{config.Config.Constants.API_BASE_URL}/api/{name}",
        "api_name": name,
    }


@app.post("/update-api-ttl", response_model=UpdateApiTtlResponse)
async def update_ttl(
    data: UpdateApiTtlRequest,
    user: UserSession = Depends(get_current_user),
):
    """Update how long an API is cached for before being refreshed"""
    user_fields = user_helpers.fetch_fields_for_user(user.email, ["premium", "userId"])
    api = api_manager.get_sheet_api_info(data.name)

    # Additional validation for non-premium users
    if not user_fields.premium and data.cdn_ttl < 60:
        raise fastapi.HTTPException(
            status_code=422,
            detail="Invalid refresh duration. Non-premium users must set a value of 60 seconds or greater.",
        )

    if api is None:
        raise fastapi.HTTPException(
            500, f"API with name {data.name} does not exist and cannot be updated."
        )

    # Check authorization based on ownership type
    if api.is_org_sheet:
        if not organization_helpers.is_organization_member(
            api.org_id, user_fields.userId
        ):
            raise fastapi.HTTPException(
                403,
                f"User with email {user.email} is not a member of the organization that owns this API",
            )
    else:
        if api.email != user.email:
            raise fastapi.HTTPException(
                401,
                f"User with email {user.email} not authorized to update API {data.name}",
            )

    api_manager.update_sheet_api_ttl(data.name, data.cdn_ttl)
    return UpdateApiTtlResponse(
        message=f"TTL for API '{data.name}' successfully updated to {data.cdn_ttl} seconds."
    )


# TODO: DELETE method was having issues with credentials. The user was not
# being passed. This should be a DELETE method, but for now we use GET.
@app.get("/delete-api/{name}")
async def delete_api(name: str, user: UserSession = Depends(get_current_user)):
    user_fields = user_helpers.fetch_fields_for_user(user.email, ["userId"])
    api = api_manager.get_sheet_api_info(name)
    if api is None:
        raise fastapi.HTTPException(
            404, f"API with name {name} does not exist and cannot be deleted."
        )

    # Check authorization based on ownership type
    if api.is_org_sheet:
        if not organization_helpers.is_organization_member(
            api.org_id, user_fields.userId
        ):
            raise fastapi.HTTPException(
                403,
                f"User with email {user.email} is not a member of the organization that owns this API",
            )
    else:
        if api.email != user.email:
            raise fastapi.HTTPException(
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


@app.get("/get-api-invocations")
def get_sheet_invocations(api_name: str, start_time: str):
    date_regex = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    if not re.match(date_regex, start_time):
        raise fastapi.HTTPException(
            status_code=400, detail="Invalid start time format. Use ISO 8601 format."
        )

    return analytics_handler.get_api_logs(api_name, start_time)


@app.get("/get-api-invocations-total")
def get_sheet_invocations_total(api_name: str):
    return analytics_handler.get_api_total_invocations(api_name)


@app.post("/create-organization", response_model=OrganizationResponse)
async def create_organization(
    data: CreateOrganizationRequest, user: UserSession = Depends(get_current_user)
):
    """Create a new organization.

    The current user will automatically be added as an admin of the organization.
    """
    user_fields = user_helpers.fetch_fields_for_user(
        user.email, ["PK", "SK", "userId", "email", "premium"]
    )

    if not user_fields.premium:
        raise fastapi.HTTPException(401, detail="Only premium members can create orgs.")

    org = organization_helpers.create_organization(data.name, user_fields)

    for email in data.invitees:
        if email == user.email:
            continue  # already added as admin
        try:
            user_id = user_helpers.lookup_user_id_by_email(email)
            organization_helpers.add_user_to_organization(
                org_id=org.orgId, email=email, user_id=user_id
            )
        except user_helpers.UserNotFound:
            logger.warning(f"User ${email} not found. Cannot add to org {org.orgId}")

    return OrganizationResponse(
        id=org.orgId, name=org.name, created_at=org.createdAt, created_by=org.createdBy
    )


@app.get("/organizations", response_model=List[OrganizationResponse])
async def get_user_organizations(user: UserSession = Depends(get_current_user)):
    """Get all organizations the current user is a member of."""
    user_id = user_helpers.lookup_user_id_by_email(user.email)
    memberships = organization_helpers.get_user_organizations(user_id)

    # For each membership, get the organization details
    organizations = []
    for membership in memberships:
        org = organization_helpers.get_organization(membership.orgId)
        if org:
            organizations.append(
                OrganizationResponse(
                    id=org.orgId,
                    name=org.name,
                    created_at=org.createdAt,
                    created_by=org.createdBy,
                )
            )

    return organizations


@app.get("/organization/{org_id}", response_model=OrganizationMembersResponse)
async def get_organization_details(org_id: str, _=Depends(check_if_org_member)):
    """Get details about an organization, including its members."""
    org = organization_helpers.get_organization(org_id)
    members = organization_helpers.get_organization_members(org_id)

    org_response = OrganizationResponse(
        id=org.orgId, name=org.name, created_at=org.createdAt, created_by=org.createdBy
    )

    member_responses = [
        OrganizationMemberResponse(
            user_id=member.userId,
            email=member.email,
            role=member.role,
            joined_at=member.joinedAt,
        )
        for member in members
    ]

    return OrganizationMembersResponse(
        organization=org_response, members=member_responses
    )


@app.post("/organization/{org_id}/invite")
async def invite_user_to_organization(
    org_id: str, email: EmailStr = fastapi.Form(...), _=Depends(check_if_org_member)
):
    """Invite a user to an organization."""
    try:
        invite_user_id = user_helpers.lookup_user_id_by_email(email)
        organization_helpers.add_user_to_organization(
            org_id=org_id, email=email, user_id=invite_user_id, role="member"
        )
        return {"message": f"User {email} has been added to the organization."}
    except user_helpers.UserNotFound:
        return {"message": f"User not found, skipping"}


@app.delete("/organization/{org_id}")
async def delete_organization(
    org_id: str,
    user_id=Depends(check_if_org_member),
):
    """Delete an organization.

    This will delete the organization, all its memberships and sheets.
    Only organization admins can delete an organization.
    """
    try:
        organization_helpers.delete_organization(org_id, user_id)
        return {"message": f"Organization with ID {org_id} has been deleted."}
    except organization_helpers.NotOrganizationMember as e:
        raise fastapi.HTTPException(status_code=403, detail=str(e))  # not admin


@app.post("/stripe-webhook")
async def webhook_received(
    request: Request, stripe_signature: str = fastapi.Header(None)
):
    data = await request.body()
    try:
        event = stripe_helpers.get_event(payload=data, header=stripe_signature)
    except stripe.SignatureVerificationError as error:
        raise fastapi.HTTPException(400, detail=str(error))

    event_type = event["type"]
    if event_type == "checkout.session.completed":
        user_email = event.data.object["customer_details"]["email"]
        stripe_helpers.upgrade_user(user_email, api_manager)
    elif event_type == "customer.subscription.deleted":
        customer_id = event.data.object["customer"]
        stripe_helpers.downgrade_user(customer_id, api_manager)
    else:
        logger.info(f"unhandled event: {event_type}")

    return {"status": "success"}


def _generate_sheet_list_items(
    sheets: list[dynamodb_sheet_repo.SheetMetadataWithWorksheets],
) -> str:
    """Generate HTML list items for each sheet."""
    if not sheets:
        return "<li>No sheets found</li>"

    items = []
    for sheet in sheets:
        items.append(
            f"""
            <li class="sheet-item">
                <strong>{sheet.spreadsheetName}</strong><br>
                Sheet ID: {sheet.sheetId}<br>
                <a class="sheet-link" href="/api/{sheet.apiName}" target="_blank">View API</a>
            </li>
        """
        )
    return "\n".join(items)


# This handler exports the FastAPI app to a Lambda handler
# allowing it to be run as a serverless function. If run via
# ECS, we can use `fastapi dev ...` instead.
handler = mangum.Mangum(app)
