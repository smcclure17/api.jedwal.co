import logging
import re

from sheetsapi import (
    auth_utils,
    dynamodb_client,
    user_helpers,
    google_sheets,
    config,
    analytics_client,
    sentry_helpers,
    stripe_helpers,
)

import fastapi
import gspread
import mangum
import stripe
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

config.Config.init()
sentry_helpers.init()

oauth = OAuth(config.Config.to_starlette_config())
sheets_handler = google_sheets.GoogleSheets()
analytics_handler = analytics_client.AnalyticsClient()


app = fastapi.FastAPI()

app.add_middleware(
    SessionMiddleware, secret_key=config.Config.Constants.OAUTH_SECRET_TOKEN
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        config.Config.Constants.CLIENT_BASE_URL,
        config.Config.Constants.CLIENT_APP_BASE_URL,
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

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def homepage(request: Request):
    user: dict | None = request.session.get("user")
    if user is not None:
        html = f"""
        <style>
            body {{
                font-family: sans-serif;
            }}
        </style>
        <h1>Google Sheets API</h1>
        <h2>Hello, {user.get("given_name")}!</h2>
        <form action="/create-api" method="post">
            <input type="text" name="sheet_id" placeholder="Google Sheet ID" style="width: 400px;">
            <button type="submit">Create API</button>
        </form>
        <a href="/logout">logout</a>
        """

        return HTMLResponse(html)
    return HTMLResponse('<a href="/login" style="font-family: sans-serif;">login</a>')


@app.get("/login")
async def login(request: Request):
    redirect_uri = f"{config.Config.Constants.API_BASE_URL}/auth"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline"
    )


@app.get("/auth")
async def auth(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        request.session.pop("user", None)
        logger.error(f"Error: {e.error}")
        return HTMLResponse(f"<h1>Something went wrong {e.error}</h1>")
    user = token.get("userinfo")
    access_token = token.get("access_token")
    if user:
        request.session["refresh_token"] = token.get("refresh_token")
        request.session["user"] = dict(user)
        request.session["access_token"] = access_token

    user_helpers.persist_user_if_not_exists(user, request)
    return RedirectResponse(url=config.Config.Constants.CLIENT_APP_BASE_URL)


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    request.session.pop("refresh_token", None)
    return RedirectResponse(url=config.Config.Constants.CLIENT_BASE_URL)


@app.get("/get-user-data")
def check_auth(request: Request):
    user = request.session.get("user")
    if user is None:
        raise fastapi.HTTPException(status_code=401, detail="Not authenticated")
    return {
        "name": user.get("given_name"),
        "email": user.get("email"),
    }


@app.get("/api/{name}")
def read_sheet(name: str, worksheet: str = "Sheet1"):
    try:
        data = sheets_handler.get_sheet_data(name, worksheet)
        print(data)
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
    except google_sheets.SheetNotFound as e:
        raise fastapi.HTTPException(status_code=404, detail="Sheet API not found.")


@app.get("/get-user-sheets")
def get_user_sheets(request: Request):
    user: dict | None = request.session.get("user")
    if user is None:
        raise fastapi.HTTPException(status_code=401, detail="Not authenticated")

    return sheets_handler.get_sheets_for_email(user.get("email"))


@app.post("/create-api")
def create_api(request: Request, sheet_id: str = fastapi.Form(...)):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    user: dict | None = request.session.get("user")

    if not access_token or not user:
        raise fastapi.HTTPException(401, "Not Authenticated")

    email = user.get("email")
    user_fields = user_helpers.fetch_fields_for_user(
        email, ["refresh_token", "premium", "api_count"]
    )

    # TODO: Need to think about what to do if a user:
    # - Goes premium
    # - Makes 10 APIs
    # - Cancels premium
    # Do we "freeze" the most recent X APIs?
    if not user_fields["premium"] and user_fields["api_count"] >= 3:
        raise fastapi.HTTPException(
            403, detail="Non-premium users may only create up to 3 APIs."
        )

    if not refresh_token:
        refresh_token = user_fields["refresh_token"]

    auth_creds = auth_utils.GoogleOauthFields.from_tokens(
        access_token=access_token,
        refresh_token=refresh_token,
    )

    # Hack: parse the sheet ID from the URL if it's a Google Sheets URL
    if "docs.google.com/spreadsheets/d/" in sheet_id:
        sheet_id = sheet_id.split("/d/")[1].split("/")[0]

    try:
        name = sheets_handler.add_sheet_to_repository(auth_creds, sheet_id, email)
    except google_sheets.SheetAlreadyExists as e:
        name = sheets_handler.get_sheet_name_from_id(sheet_id)

    return {
        "url": f"{config.Config.Constants.API_BASE_URL}/api/{name}",
        "api_name": name,
    }


@app.delete("/api/{name}")
def delete_api(request: Request, name: str):
    access_token = request.session.get("access_token")
    user: dict | None = request.session.get("user")

    if not access_token or not user:
        raise fastapi.HTTPException(401, "Not Authenticated")

    repo = dynamodb_client.DynamoDBClient()
    user_email = user.get("email")
    key = {"id": f"sheet-{name}"}
    api = repo.get_item(config.Config.Constants.SHEETS_API_TABLE, key=key)

    if api is None:
        raise fastapi.HTTPException(
            f"API with name {name} does not exist and cannot be deleted."
        )
    if api["email"] != user_email:
        raise fastapi.HTTPException(
            401, f"User with email {user_email} not authorized to delete api {name}"
        )
    repo.delete_item(config.Config.Constants.SHEETS_API_TABLE, key=key)


@app.get("/get-api-info")
def get_api_info(request: Request, name: str = fastapi.Query(...)):
    user: dict | None = request.session.get("user")
    if user is None:
        raise fastapi.HTTPException(status_code=401, detail="Not authenticated")

    try:
        api, worksheets = sheets_handler.get_sheet_info(name)
    except google_sheets.SheetNotFound as e:
        raise fastapi.HTTPException(status_code=404, detail="Sheet API not found.")
    if api["email"] != user.get("email"):
        raise fastapi.HTTPException(status_code=404, detail="Sheet API not found.")
    return {
        "api_name": api["api_name"],
        "sheet_id": api["sheet_id"],
        "worksheets": worksheets,
        "spreadsheet_name": api["spreadsheet_name"],
        "cdn_ttl": api["cdn_ttl"],
    }


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
        stripe_helpers.upgrade_user(user_email)
    elif event_type == "customer.subscription.deleted":
        customer_id = event.data.object["customer"]
        stripe_helpers.downgrade_user(customer_id)
    else:
        print(f"unhandled event: {event_type}")

    return {"status": "success"}


# This handler exports the FastAPI app to a Lambda handler
# allowing it to be run as a serverless function. If run via
# ECS, we can use `fastapi dev ...` instead.
handler = mangum.Mangum(app)
