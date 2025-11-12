"""Service layer for category operations."""

from fastapi import HTTPException, status

from jedwal.database.core import DbTable
from jedwal.posts import repository as posts_repository
from jedwal.posts.categories import repository
from jedwal.posts.categories.models import CategoryRead


def add_category_to_post(
    *, table: DbTable, owner_id: str, post_key: str, category: str
) -> None:
    """Add a category to a post.

    Creates adjacency list relationships AND updates denormalized categories on Post.
    This enables both fast reads and category-based queries.
    """
    # Verify post exists and get current categories
    post = posts_repository.get_post(table=table, owner_id=owner_id, post_id=post_key)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with key {post_key} not found",
        )

    # Add the category relationship (adjacency list for queries)
    repository.add_category_to_post(
        table=table, owner_id=owner_id, post_key=post_key, category=category
    )

    # Update denormalized categories on Post item
    current_categories = post.categories or []
    if category not in current_categories:
        current_categories.append(category)
        posts_repository.update_post(
            table=table,
            owner_id=owner_id,
            post_key=post_key,
            updates={"categories": current_categories},
        )


def remove_category_from_post(
    *, table: DbTable, owner_id: str, post_key: str, category: str
) -> None:
    """Remove a category from a post.

    Deletes adjacency list relationships AND updates denormalized categories on Post.
    Idempotent - does not raise an error if the relationship doesn't exist.
    """
    # Delete the category relationship (adjacency list)
    repository.delete_category_from_post(
        table=table, owner_id=owner_id, post_key=post_key, category=category
    )

    # Update denormalized categories on Post item
    post = posts_repository.get_post(table=table, owner_id=owner_id, post_id=post_key)
    if post and post.categories:
        current_categories = post.categories
        if category in current_categories:
            current_categories.remove(category)
            posts_repository.update_post(
                table=table,
                owner_id=owner_id,
                post_key=post_key,
                updates={"categories": current_categories},
            )


def get_categories_for_post(
    *, table: DbTable, owner_id: str, post_key: str
) -> list[CategoryRead]:
    """Get all categories for a post.

    Reads from denormalized categories field on Post item (fast, single query).
    Falls back to adjacency list query if denormalized field is empty (migration path).
    """
    # Get post with denormalized categories
    post = posts_repository.get_post(table=table, owner_id=owner_id, post_id=post_key)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with key {post_key} not found",
        )

    # Try denormalized categories first (fast path)
    if post.categories is not None:
        return [CategoryRead(category=cat) for cat in post.categories]

    # Fallback: Query adjacency list (for posts created before denormalization)
    categories = repository.get_categories_for_post(
        table=table, owner_id=owner_id, post_key=post_key
    )

    # Backfill denormalized field if we found categories in adjacency list
    if categories:
        posts_repository.update_post(
            table=table,
            owner_id=owner_id,
            post_key=post_key,
            updates={"categories": categories},
        )

    return [CategoryRead(category=cat) for cat in categories]


def get_posts_for_category(*, table: DbTable, owner_id: str, category: str) -> list:
    """Get all posts that have a specific category.

    Uses batch_get to efficiently fetch Post objects (avoids N+1).
    Returns full Post objects, not just keys.
    """

    # Get post keys from adjacency list (1 query)
    post_keys = repository.get_post_keys_for_category(
        table=table, owner_id=owner_id, category=category
    )

    if not post_keys:
        return []

    # Batch get all Post objects (1 batch request)
    posts = posts_repository.batch_get_posts(
        table=table, owner_id=owner_id, post_keys=post_keys
    )

    return posts


def delete_all_categories_for_post(
    *, table: DbTable, owner_id: str, post_key: str
) -> int:
    """Delete all categories for a post.

    Typically called when deleting a post.
    Returns the number of categories deleted.
    """
    return repository.delete_all_categories_for_post(
        table=table, owner_id=owner_id, post_key=post_key
    )
