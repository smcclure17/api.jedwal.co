from datetime import datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import AccountId, RefreshTokenInfo
from jedwal.common.exceptions import ConflictException, NotFoundException
from jedwal.posts.models import Post, PostKey


def to_item(*, post: Post) -> dict:
    """Convert domain model to DynamoDB item with keys."""
    # PK format: DOC#{owner_id}#{post_key}
    doc_key = f"DOC#{post.owner_id}#{post.post_key}"

    item = {
        "PK": doc_key,
        "SK": doc_key,
        "post_key": post.post_key,
        "doc_api_name": post.post_key,  # Keep for backward compatibility
        "owner_id": post.owner_id,
        "google_doc_id": post.google_doc_id,
        "google_doc_payload": post.google_doc_payload,
        "google_doc_ast": post.google_doc_ast,
        "title": post.title,
        "creator": post.creator,
        "refresh_token_info": post.refresh_token_info.to_dict(),
        "frozen": post.frozen,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
        # GSI2 for looking up posts by owner
        "GSI2PK": f"ACCOUNT#{post.owner_id}",
        "GSI2SK": doc_key,
    }

    # Only add categories if it exists (optional field)
    if post.categories is not None:
        item["categories"] = post.categories

    return item


def from_item(*, item: dict) -> Post:
    """Convert DynamoDB item to Post domain model."""
    # updated_at might not exist in db, so just set it if not
    updated_stamp = item.get("updated_at", datetime.now().isoformat())

    # Prefer post_key field, fallback to extracting from PK for backward compatibility
    post_key = item.get("post_key")
    if post_key is None:
        # Fallback: Extract from PK format: DOC#{owner_id}#{post_key}
        pk_parts = item["PK"].split("#")
        post_key = pk_parts[2] if len(pk_parts) >= 3 else item["PK"]

    return Post(
        post_key=post_key,
        owner_id=item["owner_id"],
        google_doc_id=item["google_doc_id"],
        google_doc_payload=item["google_doc_payload"],
        google_doc_ast=item["google_doc_ast"],
        title=item["title"],
        creator=item.get("creator", "Unknown"),
        refresh_token_info=RefreshTokenInfo(**item["refresh_token_info"]),
        frozen=item.get("frozen", False),
        categories=item.get("categories"),  # Denormalized categories
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(updated_stamp),
    )


def get_post(*, table: Table, owner_id: AccountId, post_id: PostKey) -> Post | None:
    """Get an Post by its key."""
    sheet_key = f"DOC#{owner_id}#{post_id}"
    response = table.get_item(Key={"PK": sheet_key, "SK": sheet_key})
    item = response.get("Item", None)
    if item is None:
        return None
    return from_item(item=item)


def get_posts_by_owner(*, table: Table, owner_id: AccountId) -> list[Post]:
    """
    Get all Posts owned by a specific account.

    Uses GSI2 with a filter to ensure only DOC resources are returned,
    excluding other resource types that might belong to the same owner.
    """
    response = table.query(
        IndexName="GSI2",
        KeyConditionExpression="GSI2PK = :owner_pk",
        FilterExpression="begins_with(PK, :resource_type)",
        ExpressionAttributeValues={
            ":owner_pk": f"ACCOUNT#{owner_id}",
            ":resource_type": "DOC#",
        },
    )

    items = response.get("Items", [])
    return [from_item(item=item) for item in items]


def batch_get_posts(
    *, table: Table, owner_id: AccountId, post_keys: list[str]
) -> list[Post]:
    """
    Get multiple Posts by their keys using batch_get_item.

    Efficiently fetches up to 100 posts in a single request.
    For more than 100, automatically batches.
    """
    if not post_keys:
        return []

    # Build keys for batch get
    keys = [
        {"PK": f"DOC#{owner_id}#{post_key}", "SK": f"DOC#{owner_id}#{post_key}"}
        for post_key in post_keys
    ]

    posts = []

    # DynamoDB batch_get_item has a limit of 100 items
    # Process in chunks of 100
    for i in range(0, len(keys), 100):
        batch_keys = keys[i : i + 100]

        response = table.meta.client.batch_get_item(
            RequestItems={table.name: {"Keys": batch_keys}}
        )

        # Process returned items
        for item in response.get("Responses", {}).get(table.name, []):
            posts.append(from_item(item=item))

    return posts


def get_post_by_google_doc_id(
    *, table: Table, owner_id: AccountId, google_doc_id: str
) -> Post | None:
    """
    Find a Post by Google Doc ID for a specific owner.

    Queries all Posts for the owner via GSI2, then filters by google_doc_id.
    This is performant because users typically have ~1-100 Posts max.
    """
    response = table.query(
        IndexName="GSI2",
        KeyConditionExpression="GSI2PK = :owner",
        FilterExpression="google_doc_id = :doc_id",
        ExpressionAttributeValues={
            ":owner": f"ACCOUNT#{owner_id}",
            ":doc_id": google_doc_id,
        },
    )

    items = response.get("Items", [])
    if not items:
        return None

    return from_item(item=items[0])


def delete_post(*, table: Table, owner_id: AccountId, post_key: PostKey) -> None:
    """Delete a Post from the db."""
    sheet_key = f"DOC#{owner_id}#{post_key}"
    try:
        table.delete_item(
            Key={
                "PK": sheet_key,
                "SK": sheet_key,
            },
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(f"Post with key {post_key} not found") from e
        raise


def create_post(*, table: Table, post: Post) -> Post:
    """Create a new Post in the db."""
    item = to_item(post=post)

    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictException(
                f"API with key {post.post_key} already exists"
            ) from e
        raise

    return post


def update_post(
    *, table: Table, owner_id: AccountId, post_key: PostKey, updates: dict
) -> Post:
    """Update an existing Post with partial updates."""
    # First, get the existing Post
    existing_post = get_post(table=table, owner_id=owner_id, post_id=post_key)
    if existing_post is None:
        raise NotFoundException(f"Post with key {post_key} not found")

    # Build update expression dynamically
    update_expressions = []
    expression_attribute_names = {}
    expression_attribute_values = {}

    # Add updated_at timestamp
    updates["updated_at"] = datetime.now().isoformat()

    for key, value in updates.items():
        placeholder = f"#{key}"
        value_placeholder = f":{key}"
        update_expressions.append(f"{placeholder} = {value_placeholder}")
        expression_attribute_names[placeholder] = key
        expression_attribute_values[value_placeholder] = value

    sheet_key = f"DOC#{owner_id}#{post_key}"

    try:
        response = table.update_item(
            Key={"PK": sheet_key, "SK": sheet_key},
            UpdateExpression="SET " + ", ".join(update_expressions),
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(f"Post with key {post_key} not found") from e
        raise

    return from_item(item=response["Attributes"])
