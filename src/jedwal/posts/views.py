from fastapi import APIRouter, Response, status

from jedwal.account.models import AccountId
from jedwal.auth.service import VerifiedAccount
from jedwal.common.exceptions import NotFoundException
from jedwal.database.core import DbTable, SqSClient
from jedwal.posts import service
from jedwal.posts.categories.views import authenticated_categories_router
from jedwal.posts.models import (
    PostCreate,
    PostCreateRead,
    PostCreateRequest,
    PostDocumentDataRead,
    PostKey,
    PostRead,
)
from jedwal.posts.webhooks.views import authenticated_webhooks_router

public_posts_router = APIRouter(prefix="/posts", tags=["public"])
authenticated_posts_router = APIRouter(prefix="/posts", tags=["posts"])

authenticated_posts_router.include_router(
    authenticated_categories_router, prefix="/{post_key}"
)
authenticated_posts_router.include_router(
    authenticated_webhooks_router, prefix="/{post_key}"
)


@public_posts_router.get("/{post_id}", response_model=PostDocumentDataRead)
async def get_post_data(
    account_id: AccountId,
    post_id: PostKey,
    table: DbTable,
):
    """Get data from a sheet API endpoint."""
    post = service.get_post(table=table, owner_id=account_id, post_id=post_id)
    if post is None:
        raise NotFoundException(detail=[{"msg": "Post not found"}])
    return service.get_post_data(table=table, post=post)


@public_posts_router.head("/{post_id}")
async def head_post_data(
    account_id: AccountId,
    post_id: PostKey,
    table: DbTable,
):
    """Check if a post exists without returning its data."""
    post = service.get_post(table=table, owner_id=account_id, post_id=post_id)
    if post is None:
        raise NotFoundException(detail=[{"msg": "Post not found"}])
    return Response(status_code=status.HTTP_200_OK)


# TODO: maybe de-dup public and private doc listing routes
@public_posts_router.get("", response_model=list[PostRead])
async def get_public_posts_for_account(
    account_id: AccountId,
    table: DbTable,
    categories: str | None = None,
):
    """Get all APIs for an account."""
    posts = service.get_posts_for_account(table=table, owner_id=account_id)
    filter_categories: list[str] | None = None
    if categories:
        filter_categories = [cat.strip() for cat in categories.split(",")]

    res = []
    for post in posts:
        if filter_categories:
            api_categories_set = set(post.categories or [])
            filter_categories_set = set(filter_categories)

            if not filter_categories_set.issubset(api_categories_set):
                continue
        res.append(post)
    return res


@authenticated_posts_router.post("/{post_id}/refresh", response_model=None)
async def refresh_post_data(
    account_id: AccountId,
    post_id: PostKey,
    table: DbTable,
    queue: SqSClient,
    image_handler: service.PostImageHandler,
):
    service.refresh_post_data(
        queue=queue,
        table=table,
        owner_id=account_id,
        post_id=post_id,
        image_handler=image_handler,
    )


@authenticated_posts_router.get("", response_model=list[PostRead])
async def get_posts_for_account(
    account_id: AccountId,
    table: DbTable,
):
    """Get all APIs for an account."""
    return service.get_posts_for_account(table=table, owner_id=account_id)


@authenticated_posts_router.post(
    "", response_model=PostCreateRead, status_code=status.HTTP_201_CREATED
)
async def create_post(
    account_id: AccountId,
    request: PostCreateRequest,
    table: DbTable,
    verified_account: VerifiedAccount,
    image_handler: service.PostImageHandler,
):
    """Create a new API endpoint for a Google Sheet.

    The account_id from the path determines the owner of the API.
    User must have permissions to manage this account (self or org).
    """
    post_create = PostCreate(
        owner_id=account_id,  # Owner comes from path, not request body
        post_key=request.post_key,
        google_doc_id=request.google_doc_id,
        refresh_token_info=verified_account.refresh_token_info,
    )

    account = service.create_post(table=table, post_create=post_create, image_handler=image_handler)
    return {"post_key": account.post_key}


@authenticated_posts_router.delete("/{post_id}", response_model=None)
async def delete_api(
    account_id: AccountId,
    post_id: PostKey,
    table: DbTable,
):
    """Delete an API endpoint."""
    service.delete_post(table=table, owner_id=account_id, post_id=post_id)
