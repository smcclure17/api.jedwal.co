"""Repository layer for category-post relationships."""

from mypy_boto3_dynamodb.service_resource import Table

from jedwal.posts.categories.models import CategoryPostRelationship


def to_items(*, relationship: CategoryPostRelationship) -> list[dict]:
    """Convert relationship to two DynamoDB items (bidirectional).

    Creates both forward and reverse relationships:
    1. Category -> Post (for listing posts in a category)
    2. Post -> Category (for listing categories for a post)
    """
    # Forward relationship: Category -> Post
    category_to_post = {
        "PK": f"CATEGORY#{relationship.owner_id}#{relationship.category}",
        "SK": f"POST#{relationship.post_key}",
        "GSI1PK": f"POST#{relationship.owner_id}#{relationship.post_key}",
        "GSI1SK": f"CATEGORY#{relationship.category}",
        "owner_id": relationship.owner_id,
        "post_key": relationship.post_key,
        "category": relationship.category,
        "relationship_type": "category_to_post",
    }

    # Reverse relationship: Post -> Category
    post_to_category = {
        "PK": f"POST#{relationship.owner_id}#{relationship.post_key}",
        "SK": f"CATEGORY#{relationship.category}",
        "GSI1PK": f"CATEGORY#{relationship.owner_id}#{relationship.category}",
        "GSI1SK": f"POST#{relationship.post_key}",
        "owner_id": relationship.owner_id,
        "post_key": relationship.post_key,
        "category": relationship.category,
        "relationship_type": "post_to_category",
    }

    return [category_to_post, post_to_category]


def add_category_to_post(
    *, table: Table, owner_id: str, post_key: str, category: str
) -> None:
    """Add a category to a post (creates bidirectional relationship)."""
    relationship = CategoryPostRelationship(
        owner_id=owner_id,
        post_key=post_key,
        category=category,
        relationship_type="category_to_post",  # Placeholder, both types created
    )

    items = to_items(relationship=relationship)

    # Use batch writer for atomic creation of both relationships
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)


def delete_category_from_post(
    *, table: Table, owner_id: str, post_key: str, category: str
) -> None:
    """Remove a category from a post (deletes both relationship directions)."""
    keys_to_delete = [
        {
            # Forward relationship: Category -> Post
            "PK": f"CATEGORY#{owner_id}#{category}",
            "SK": f"POST#{post_key}",
        },
        {
            # Reverse relationship: Post -> Category
            "PK": f"POST#{owner_id}#{post_key}",
            "SK": f"CATEGORY#{category}",
        },
    ]

    # Use batch writer for atomic deletion of both relationships
    with table.batch_writer() as batch:
        for key in keys_to_delete:
            batch.delete_item(Key=key)


def get_categories_for_post(
    *, table: Table, owner_id: str, post_key: str
) -> list[str]:
    """Get all categories for a specific post using adjacency list pattern."""
    pk = f"API#{owner_id}#{post_key}"  # TODO: this should really be DOC, not api

    response = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": pk},
    )

    categories = []
    for item in response.get("Items", []):
        # SK format is "CATEGORY#{category}"
        sk = item["SK"]
        if sk.startswith("CATEGORY#"):
            category = sk.replace("CATEGORY#", "")
            categories.append(category)

    return categories


def get_post_keys_for_category(
    *, table: Table, owner_id: str, category: str
) -> list[str]:
    """Get all post keys for a specific category using adjacency list pattern.

    Returns just the post keys. Use get_posts_for_category() in service layer
    to get full Post objects with batch_get.
    """
    pk = f"CATEGORY#{owner_id}#{category}"

    response = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": pk},
    )

    post_keys = []
    for item in response.get("Items", []):
        # SK format is "POST#{post_key}"
        sk = item["SK"]
        if sk.startswith("API#"):
            post_key = sk.replace("POST#", "")
            post_keys.append(post_key)

    return post_keys


def delete_all_categories_for_post(
    *, table: Table, owner_id: str, post_key: str
) -> int:
    """Delete all category relationships for a post.

    Useful when deleting a post entirely.
    Returns the number of categories deleted.
    """
    # First, get all categories for the post
    categories = get_categories_for_post(
        table=table, owner_id=owner_id, post_key=post_key
    )

    if not categories:
        return 0

    # Delete all relationships
    with table.batch_writer() as batch:
        for category in categories:
            # Delete both directions
            batch.delete_item(
                Key={
                    "PK": f"CATEGORY#{owner_id}#{category}",
                    "SK": f"POST#{post_key}",
                }
            )
            batch.delete_item(
                Key={
                    "PK": f"POST#{owner_id}#{post_key}",
                    "SK": f"CATEGORY#{category}",
                }
            )

    return len(categories)
