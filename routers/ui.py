"""
UI-related routes and HTML rendering.
"""

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import HTMLResponse

from sheetsapi import config, sheet_api_repo_v2

router = APIRouter(tags=["ui"])
manager_v2 = sheet_api_repo_v2.SheetApiRepo.from_table_name(
    config.Config.Constants.SHEETS_API_TABLE
)


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Render simple homepage"""
    user: dict | None = request.session.get("user")
    if user is not None:
        sheets = manager_v2.get_sheet_apis_for_account(user["sub"])
        html = f"""
        <style>
            body {{
                font-family: sans-serif;
            }}
        </style>
        <h1>Google Sheets API</h1>
        <h2>Hello, {user.get("given_name")}!</h2>
        <form action="/create-api" method="post">
            <input type="text" name="google_sheet_id" placeholder="Enter Google Sheet ID" style="width: 400px;">
            <button type="submit">Create API</button>
        </form>
        <h3>Your Sheets:</h3>
        <ul class="sheet-list">
        </ul>
        <a href="/logout">logout</a>
        """

        return HTMLResponse(html)
    return HTMLResponse(
        '<a href="/login" style="font-family: sans-serif;">please login</a>'
    )
