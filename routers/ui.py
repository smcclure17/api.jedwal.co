"""
UI-related routes and HTML rendering.
"""

import os
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from sheetsapi import sheet_api_repo_v2

# Get the directory of the current file and compute the path to the public directory
BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"

router = APIRouter(tags=["ui"])
manager_v2 = sheet_api_repo_v2.SheetApiRepo.from_table_name()


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Render simple homepage"""
    user: dict | None = request.session.get("user")
    if user is not None:
        sheets = manager_v2.get_sheet_apis_for_account(user["sub"])
        html = f"""
        <html>
        <head>
            <title>Jedwal.co API</title>
            <link rel="icon" href="/favicon.ico" type="image/x-icon">
            <style>
                body {{
                    font-family: sans-serif;
                }}
            </style>
        </head>
        <body>
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
        </body>
        </html>
        """

        return HTMLResponse(html)
    return HTMLResponse(
        """
        <html>
        <head>
            <title>Jedwal.co API - Login</title>
            <link rel="icon" href="/favicon.ico" type="image/x-icon">
            <style>
                body {
                    font-family: sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }
                a {
                    padding: 10px 20px;
                    background-color: #4285f4;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                }
            </style>
        </head>
        <body>
            <a href="/login">Login with Google</a>
        </body>
        </html>
    """
    )


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon.ico from the public directory."""
    favicon_path = PUBLIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    # Return a 404 if favicon doesn't exist
    return HTMLResponse(status_code=404)
