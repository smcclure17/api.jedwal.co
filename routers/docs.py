"""
Doc API management routes and operations.
"""

from datetime import datetime
import json
from typing import Annotated, Optional
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
import sentry_sdk

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
    AddCategoryToDocRequest,
    AddWebhookToDocApiRequest,
    DeleteWebhookToDocApiRequest,
    DocApiPublicResponse,
    DocApiResponse,
    PublishDocApiRequest,
    UpdateApiTtlResponse,
    UpdateDocApiSlugRequest,
)
from sheetsapi.models.db_models import WebhookIntegration
from sheetsapi.parsers.doc_ast import (
    ElementType,
    GoogleDocsParser,
    Node,
    node_to_dict,
    dict_to_node,
)
from sheetsapi.parsers.doc_to_md import MarkdownRenderer
from sheetsapi.image_handler import ImageHandler
from sheetsapi.webhook_queue import trigger_webhooks_for_doc

router = APIRouter(tags=["docs"])
cloudfront = cloudfront_helpers.create_cloudfront_client()

account_repo = AccountRepo.from_table_name()
doc_repo = DocApiRepo.from_table_name()
lru_worksheet_cache = lru_cache.LRUCache(capacity=100)
image_handler = ImageHandler()


@router.get("/doc/{owner_id}/{api_name}")
async def get_doc(owner_id: str, api_name: str):
    renderer = MarkdownRenderer()

    try:
        api = doc_repo.get_api_metadata(owner_id, api_name)
    except DocApiNotFoundError:
        raise HTTPException(404, detail="Sheet API not found.")

    if api.frozen:
        raise HTTPException(401, "API is frozen. Re-upgrade to premium to unfreeze")

    # Backwards compat: We previously didn't store the serialized AST in the DB
    # (just the raw json payload). So, if an older post doesn't have the AST stored
    # we'll need to create it here.
    if api.google_doc_ast:
        serialized_ast = json.loads(api.google_doc_ast)
        ast: Node = dict_to_node(serialized_ast)
    else:
        parser = GoogleDocsParser(
            docs_json=json.loads(api.google_doc_payload), image_handler=image_handler
        )
        ast = parser.parse()
        doc_repo.update_api(
            owner_id, api_name, {"google_doc_ast": json.dumps(node_to_dict(ast))}
        )

    output = renderer.render(ast)

    return JSONResponse(
        content={
            "content": output,
            "title": api.title,
            "published_at": api.published_at,
            "creator": api.creator,
        },
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

    ast_parser = GoogleDocsParser(google_doc_payload, image_handler=image_handler)
    google_doc_ast_json = node_to_dict(ast_parser.parse())

    # Creator/author should probably 1) be editable and 2) be the owner of the
    # Google Doc, not the user who creates the API, but that's more tricky
    # since the owner isn't returned in the Google Docs API call.
    if user.family_name:
        creator = f"{user.given_name} {user.family_name}"
    else:
        creator = f"{user.given_name}"

    sheet_api_res = doc_repo.create_api(
        owner_id=owner_id,
        google_doc_id=google_id,
        refresh_token_info=refresh_token_info,
        payload=json.dumps(google_doc_payload),
        ast_payload=json.dumps(google_doc_ast_json),
        title=google_doc_payload["title"],
        creator=creator,
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

    try:
        api_metadata = doc_repo.get_api_metadata(owner_id, api_name)
    except DocApiNotFoundError:
        raise HTTPException(
            400, f"Cannot find doc api to delete. {owner_id}/{api_name}"
        )

    # TODO: need to be either the user or an org admin to delete
    deleted_items = doc_repo.delete_api(owner_id, api_name)

    if cloudfront is not None:
        cloudfront_helpers.invalidate_cache(
            cloudfront=cloudfront,
            distribution_id=config.Config.Constants.CLOUDFRONT_DISTRIBUTION_ID,
            path=f"/doc/{owner_id}/{api_name}*",
        )

    # Get all images from AST and delete them
    # TODO: maybe move this to async/a queue to not block
    # the main thread? But, probably fine for now with small
    # number of images.
    try:
        ast: Node = dict_to_node(json.loads(api_metadata.google_doc_ast))

        def dfs_delete_images(node: Node):
            if isinstance(node, Node) and node.node_type == ElementType.IMAGE:
                image_handler.delete(node.src)

            children = getattr(node, "children", None)
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, Node):
                        dfs_delete_images(child)

        dfs_delete_images(ast)
    except Exception as e:
        sentry_sdk.capture_exception(
            Exception(
                f"failed to delete images for api {owner_id}/{api_name}. Error {e}"
            )
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


# "Public Facing" copy of metadata route for use by users
# TODO: create some kind of API key auth for this
@router.get("/docs/{owner_id}")
async def get_public_apis(owner_id: str, categories: Optional[str] = None):
    """Get all sheets owned by the current user (personal sheets only)."""

    filter_categories: Optional[list[str]] = None
    if categories:
        filter_categories = [cat.strip() for cat in categories.split(",")]

    res = []
    for api in doc_repo.get_apis_for_account(owner_id):
        if filter_categories:
            # Intersection: API must have ALL specified categories
            api_categories_set = set(api.categories or [])
            filter_categories_set = set(filter_categories)

            if not filter_categories_set.issubset(api_categories_set):
                continue

        gdocs = google_docs_client.GoogleDocs.from_token_info(api.refresh_token_info)
        title = gdocs.get_document_title(doc_id=api.google_doc_id)
        res.append(DocApiPublicResponse.from_doc_api(api, title=title))

    return {"apis": res}


@router.post("/doc/publish")
async def update_content(data: PublishDocApiRequest, user: CurrentUser):
    """Publish/update the google doc content to your API"""
    if not account_repo.check_user_access_for_owner(user.sub, data.owner_id):
        raise HTTPException(403, "Not authorized")

    api = doc_repo.get_api_metadata(data.owner_id, data.api_name)
    google_docs = google_docs_client.GoogleDocs.from_token_info(api.refresh_token_info)
    google_doc_payload = google_docs.get_document(api.google_doc_id)
    parser = GoogleDocsParser(docs_json=google_doc_payload, image_handler=image_handler)
    published_at = datetime.now().isoformat()

    try:
        updated_api = doc_repo.update_api(
            owner_id=data.owner_id,
            api_name=data.api_name,
            fields={
                "google_doc_payload": json.dumps(google_doc_payload),
                "google_doc_ast": json.dumps(node_to_dict(parser.parse())),
                "title": google_doc_payload["title"],
                "published_at": published_at,
            },
        )

        # Invalidate anything in the cache to ensure the TTL is updated right away.
        # Otherwise the TTL would not update until the old entry expires (could be days)
        if cloudfront is not None:
            cloudfront_helpers.invalidate_cache(
                cloudfront=cloudfront,
                distribution_id=config.Config.Constants.CLOUDFRONT_DISTRIBUTION_ID,
                path=f"/doc/{data.owner_id}/{data.api_name}*",
            )

        try:
            trigger_webhooks_for_doc(
                owner_id=data.owner_id,
                api_name=data.api_name,
                event_data={
                    "title": updated_api.title,
                    "published_at": updated_api.published_at,
                    "custom_slug": updated_api.custom_slug,
                },
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)

        return UpdateApiTtlResponse(message="Success!")
    except DocApiNotFoundError:
        raise HTTPException(404, "Sheet API Not Found. Cannot modify cache duration")


@router.post("/doc/add-category")
async def add_category(body: AddCategoryToDocRequest, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, body.owner_id):
        raise HTTPException(403, "Not authorized")

    doc_repo.add_category_to_api(body.owner_id, body.api_name, body.category)
    return {"success": True}


@router.delete("/doc/delete-category/{owner_id}/{api_name}")
async def add_category(owner_id: str, api_name: str, category: str, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, owner_id):
        raise HTTPException(403, "Not authorized")

    doc_repo.delete_category_from_api(owner_id, api_name, category)
    return {"success": True}


@router.post("/doc/update-slug")
async def update_doc_slug(body: UpdateDocApiSlugRequest, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, body.owner_id):
        raise HTTPException(403, "Not authorized")

    doc_repo.update_api(body.owner_id, body.api_name, {"custom_slug": body.slug})
    return {"success": True}


@router.post("/doc/add-webhook")
async def add_webhook(body: AddWebhookToDocApiRequest, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, body.owner_id):
        raise HTTPException(403, "Not authorized")

    new_webhook = WebhookIntegration(**body.webhook.model_dump())
    api_metadata = doc_repo.get_api_metadata(body.owner_id, body.api_name)
    webhooks = api_metadata.webhooks or []

    if new_webhook.url in [w.url for w in webhooks]:
        raise HTTPException(400, f"Webhook already exists for url: {new_webhook.url}")

    updated_webhooks = webhooks + [new_webhook]
    doc_repo.update_api(
        body.owner_id,
        body.api_name,
        {"webhooks": [w.model_dump() for w in updated_webhooks]},
    )

    return {"success": True}


@router.delete("/doc/delete-webhook")
async def delete_webhook(body: DeleteWebhookToDocApiRequest, user: CurrentUser):
    if not account_repo.check_user_access_for_owner(user.sub, body.owner_id):
        raise HTTPException(403, "Not authorized")

    # Get existing webhooks
    api_metadata = doc_repo.get_api_metadata(body.owner_id, body.api_name)
    webhooks = api_metadata.webhooks or []

    # Filter out the one to delete
    updated_webhooks = [w for w in webhooks if w.url != body.url]

    if len(updated_webhooks) == len(webhooks):
        raise HTTPException(404, f"No webhook found for url: {body.url}")

    # Save updated list
    doc_repo.update_api(
        body.owner_id,
        body.api_name,
        {"webhooks": [w.model_dump() for w in updated_webhooks]},
    )

    return {"success": True}
