"""API routes for category management."""

from fastapi import APIRouter, status

from jedwal.account.models import AccountId
from jedwal.database.core import DbTable
from jedwal.posts.categories import service
from jedwal.posts.categories.models import CategoryCreate, CategoryRead
from jedwal.posts.models import PostKey

# Nested under posts routes: /manage/{account_id}/posts/{post_key}/categories
authenticated_categories_router = APIRouter(
    prefix="/categories", tags=["post categories"]
)


@authenticated_categories_router.get("", response_model=list[CategoryRead])
async def get_categories_for_post(
    account_id: AccountId,
    post_key: PostKey,
    table: DbTable,
):
    """Get all categories for a specific post."""
    return service.get_categories_for_post(
        table=table, owner_id=account_id, post_key=post_key
    )


@authenticated_categories_router.post(
    "", response_model=None, status_code=status.HTTP_201_CREATED
)
async def add_category_to_post(
    account_id: AccountId,
    post_key: PostKey,
    category_create: CategoryCreate,
    table: DbTable,
):
    """Add a category to a post."""
    service.add_category_to_post(
        table=table,
        owner_id=account_id,
        post_key=post_key,
        category=category_create.category,
    )


@authenticated_categories_router.delete("/{category}", response_model=None)
async def remove_category_from_post(
    account_id: AccountId,
    post_key: PostKey,
    category: str,
    table: DbTable,
):
    """Remove a category from a post."""
    service.remove_category_from_post(
        table=table, owner_id=account_id, post_key=post_key, category=category
    )
