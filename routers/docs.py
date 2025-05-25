"""
Doc API management routes and operations.
"""

import json
from typing import Annotated
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from dependencies import CurrentUser
from sheetsapi import (
    auth_utils,
    config,
    google_docs_client,
    lru_cache,
)
from sheetsapi import cloudfront_helpers
from sheetsapi.account_repo import AccountRepo
from sheetsapi.doc_repo import DocApiNotFoundError, DocApiRepo
from sheetsapi.models.api_models import (
    DocApiResponse,
    PublishDocApiRequest,
    UpdateApiTtlResponse,
)
from sheetsapi.parsers.doc_ast import GoogleDocsParser
from sheetsapi.parsers.doc_to_md import MarkdownRenderer

router = APIRouter(tags=["docs"])
cloudfront = cloudfront_helpers.create_cloudfront_client()

account_repo = AccountRepo.from_table_name()
doc_repo = DocApiRepo.from_table_name()
lru_worksheet_cache = lru_cache.LRUCache(capacity=100)


@router.get("/doc/{owner_id}/{api_name}")
async def get_doc(owner_id: str, api_name: str, format: str = "markdown"):
    if format == "markdown":
        renderer = MarkdownRenderer()
    elif format == "json":
        renderer = MarkdownRenderer()

    try:
        api = doc_repo.get_api_metadata(owner_id, api_name)
    except DocApiNotFoundError:
        raise HTTPException(404, detail="Sheet API not found.")

    if api.frozen:
        raise HTTPException(401, "API is frozen. Re-upgrade to premium to unfreeze")

    ast = GoogleDocsParser(docs_json=json.loads(api.google_doc_payload))
    output = renderer.render(ast.parse())

    return JSONResponse(
        content={"content": output},
        headers={"Cache-Control": f"max-age=86400, public"},  # Re-pull from DB daily
        status_code=200,
    )


@router.post("/doc")
async def create_doc(
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

    # Hack: parse the sheet ID from the URL if it's a Google Sheets URL
    if "docs.google.com/document/d/" in google_id:
        google_id = google_id.split("/d/")[1].split("/")[0]

    auth = auth_utils.GoogleOauthFields.from_tokens(
        access_token=google_docs_client.EMPTY_ACCESS_TOKEN,
        refresh_token_info=refresh_token_info,
    )
    auth = auth.refresh_access_token()

    try:
        google_docs = google_docs_client.GoogleDocs.from_token_info(refresh_token_info)
        google_doc_payload = google_docs.get_document(google_id)
    except google_docs_client.DocAccessException as error:
        raise HTTPException(415, detail="Could not access Doc. Check your permissions.")

    sheet_api_res = doc_repo.create_api(
        owner_id=owner_id,
        google_doc_id=google_id,
        refresh_token_info=refresh_token_info,
        payload=json.dumps(google_doc_payload),
    )

    doc_api_name = sheet_api_res.doc_api_name
    return {
        "url": f"{config.Config.Constants.API_BASE_URL}/doc/{owner_id}/{doc_api_name}",
        "api_name": doc_api_name,
    }


@router.delete("/doc/{owner_id}/{api_name}")
async def delete_doc(owner_id: str, api_name: str, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, owner_id):
        raise HTTPException(403, "Not authorized")

    # TODO: need to be either the user or an org admin to delete
    deleted_items = doc_repo.delete_api(owner_id, api_name)

    if cloudfront is not None:
        cloudfront_helpers.invalidate_cache(
            cloudfront=cloudfront,
            distribution_id=config.Config.Constants.CLOUDFRONT_DISTRIBUTION_ID,
            path=f"/doc/{owner_id}/{api_name}*",
        )
    return deleted_items


@router.get("/docs/metadata/{owner_id}")
async def get_apis_metadata(owner_id: str, user: CurrentUser):
    """Get all sheets owned by the current user (personal sheets only)."""
    if not account_repo.check_user_access_for_owner(user.sub, owner_id):
        raise HTTPException(403, "Not authorized")

    res = []
    for api in doc_repo.get_apis_for_account(owner_id):
        gdocs = google_docs_client.GoogleDocs.from_token_info(api.refresh_token_info)
        title = gdocs.get_document_title(doc_id=api.google_doc_id)
        res.append(DocApiResponse.from_doc_api(api, title=title))
    return {"apis": res}


@router.post("/doc/publish")
async def update_content(data: PublishDocApiRequest, user: CurrentUser):
    """Publish/update the google doc content to your API"""
    if not account_repo.check_user_access_for_owner(user.sub, data.owner_id):
        raise HTTPException(403, "Not authorized")

    api = doc_repo.get_api_metadata(data.owner_id, data.api_name)
    google_docs = google_docs_client.GoogleDocs.from_token_info(api.refresh_token_info)
    google_doc_payload = google_docs.get_document(api.google_doc_id)

    try:
        doc_repo.update_api(
            owner_id=data.owner_id,
            api_name=data.api_name,
            fields={"google_doc_payload": json.dumps(google_doc_payload)},
        )

        # Invalidate anything in the cache to ensure the TTL is updated right away.
        # Otherwise the TTL would not update until the old entry expires (could be days)
        if cloudfront is not None:
            cloudfront_helpers.invalidate_cache(
                cloudfront=cloudfront,
                distribution_id=config.Config.Constants.CLOUDFRONT_DISTRIBUTION_ID,
                path=f"/doc/{data.owner_id}/{data.api_name}*",
            )

        return UpdateApiTtlResponse(message="Success!")
    except DocApiNotFoundError:
        raise HTTPException(404, "Sheet API Not Found. Cannot modify cache duration")
