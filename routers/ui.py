"""
UI-related routes and HTML rendering.
"""

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import HTMLResponse

from sheetsapi import sheet_api_manager
from sheetsapi.models.db_models import SheetMetadataWithWorksheets

router = APIRouter(tags=["ui"])
api_manager = sheet_api_manager.SheetManager()


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Render simple homepage"""
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


def _generate_sheet_list_items(sheets: list[SheetMetadataWithWorksheets]) -> str:
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
