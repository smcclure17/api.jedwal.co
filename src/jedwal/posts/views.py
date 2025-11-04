from fastapi import APIRouter, HTTPException, status

from jedwal.auth.service import VerifiedAccount
from jedwal.posts import service
from jedwal.posts.categories.views import authenticated_categories_router
from jedwal.database.core import DbTable
from jedwal.posts.models import (
    PostCreate,
    PostCreateRequest,
    PostDocumentDataRead,
    PostRead,
)

public_posts_router = APIRouter(prefix="/posts")
authenticated_posts_router = APIRouter(prefix="/posts")

authenticated_posts_router.include_router(
    authenticated_categories_router, prefix="/{post_key}"
)


@public_posts_router.get("/{post_id}", response_model=PostDocumentDataRead)
async def get_post_data(
    account_id: str,
    post_id: str,
    table: DbTable,
):
    """Get data from a sheet API endpoint."""
    post = service.get_post(table=table, owner_id=account_id, post_id=post_id)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found."
        )
    return service.get_post_data(table=table, post=post)


# TODO: maybe de-dup public and private doc listing routes
@public_posts_router.get("", response_model=list[PostRead])
async def get_apis_for_account(
    account_id: str,
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
async def refresh_post_data(account_id: str, post_id: str, table: DbTable):
    service.refresh_post_data(
        table=table,
        owner_id=account_id,
        post_id=post_id,
        image_handler=service.PostImageHandler,
    )


@authenticated_posts_router.get("", response_model=list[PostRead])
async def get_apis_for_account(
    account_id: str,
    table: DbTable,
):
    """Get all APIs for an account."""
    return service.get_posts_for_account(table=table, owner_id=account_id)


@authenticated_posts_router.post(
    "", response_model=PostRead, status_code=status.HTTP_201_CREATED
)
async def create_api(
    account_id: str,
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

    created_post, _ = service.create_api(
        table=table, post_create=post_create, image_handler=image_handler
    )

    return PostRead(
        post_key=created_post.post_key,
        owner_id=created_post.owner_id,
        title=created_post.title,
        created_at=created_post.created_at,
        updated_at=created_post.updated_at,
    )


@authenticated_posts_router.delete("", response_model=None)
async def delete_api(
    account_id: str,
    post_key: str,
    table: DbTable,
):
    """Delete an API endpoint."""
    service.delete_post(table=table, owner_id=account_id, post_id=post_key)
