"""
Doc API management routes and operations.
"""

from typing import Annotated
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse

from dependencies import CurrentUser
from sheetsapi import (
    config,
    google_docs_client,
    lru_cache,
)
from sheetsapi import cloudfront_helpers
from sheetsapi.account_repo import AccountRepo
from sheetsapi.doc_repo import DocApiRepo
from sheetsapi.parsers.doc_to_md import GoogleDocsToMarkdown
from sheetsapi.parsers.docs_to_json import GoogleDocsToJSON
from sheetsapi.sheet_repo import SheetApiNotFoundError

router = APIRouter(tags=["docs"])
cloudfront = cloudfront_helpers.create_cloudfront_client()

account_repo = AccountRepo.from_table_name()
doc_repo = DocApiRepo.from_table_name()
lru_worksheet_cache = lru_cache.LRUCache(capacity=100)


@router.get("/doc/{owner_id}/{doc_api_name}")
async def get_doc(owner_id: str, doc_api_name: str, format: str = "json"):
    if format == "markdown":
        converter = GoogleDocsToMarkdown
    elif format == "json":
        converter = GoogleDocsToJSON

    try:
        sheet_api = doc_repo.get_api_metadata(owner_id, doc_api_name)
    except SheetApiNotFoundError:
        raise HTTPException(404, detail="Sheet API not found.")

    google_doc_id = sheet_api["google_doc_id"]
    refresh_token_info = sheet_api["refresh_token_info"]
    cache_duration = sheet_api["cache_duration"]

    if sheet_api.get("frozen"):
        raise HTTPException(401, "API is frozen. Re-upgrade to premium to unfreeze")

    google_client = google_docs_client.GoogleDocs.from_token_info(refresh_token_info)
    payload = google_client.get_document(google_doc_id)
    markdown = payload
    markdown = converter(payload).convert()

    return JSONResponse(
        content={"content": markdown},
        headers={"Cache-Control": f"max-age={cache_duration}, public"},
        status_code=200,
    )


@router.post("/doc")
async def create_doc(
    doc_id: Annotated[str, Body(...)],
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

    # Hack: parse the sheet ID from the URL if it's a Google Sheets URL
    if "docs.google.com/document/d/" in doc_id:
        doc_id = doc_id.split("/d/")[1].split("/")[0]

    try:
        # Check the user has access to the Google Doc
        google_docs = google_docs_client.GoogleDocs.from_token_info(refresh_token_info)
        google_docs.get_document(doc_id)
    except google_docs_client.DocAccessException:
        raise HTTPException(
            415, detail="Cannot access Document. Please check your permissions."
        )

    sheet_api_res = doc_repo.create_api(
        owner_id=owner_id,
        google_doc_id=doc_id,
        refresh_token_info=refresh_token_info,
    )

    doc_api_name = sheet_api_res["doc_api_name"]
    return {
        "url": f"{config.Config.Constants.API_BASE_URL}/doc/{owner_id}/{doc_api_name}",
        "api_name": doc_api_name,
    }
