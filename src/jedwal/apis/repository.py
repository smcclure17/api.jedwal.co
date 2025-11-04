from datetime import datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import RefreshTokenInfo
from jedwal.apis.models import Api
from jedwal.common.exceptions import ConflictException, NotFoundException


def to_item(*, api: Api) -> dict:
    """Convert domain model to DynamoDB item with keys."""
    # PK format: SHEET#{owner_id}#{api_key}
    sheet_key = f"SHEET#{api.owner_id}#{api.api_key}"

    item = {
        "PK": sheet_key,
        "SK": sheet_key,
        "sheet_api_name": api.api_key,  # Keep for backward compatibility, same as api_key
        "owner_id": api.owner_id,
        "google_sheet_id": api.google_sheet_id,
        "refresh_token_info": api.refresh_token_info.to_dict(),
        "frozen": api.frozen,
        "cache_duration": api.cache_duration,
        "created_at": api.created_at.isoformat(),
        "updated_at": api.updated_at.isoformat(),
        # GSI2 for looking up APIs by owner
        "GSI2PK": f"ACCOUNT#{api.owner_id}",
        "GSI2SK": sheet_key,
    }

    # Only add spreadsheet_title if it exists (optional field)
    if api.spreadsheet_title is not None:
        item["spreadsheet_title"] = api.spreadsheet_title

    return item


def from_item(*, item: dict) -> Api:
    """Convert DynamoDB item to Api domain model."""
    # updated_at might not exist in db, so just set it if not
    updated_stamp = item.get("updated_at", datetime.now().isoformat())

    # Extract api_key from PK format: SHEET#{owner_id}#{api_key}
    pk_parts = item["PK"].split("#")
    api_key = pk_parts[2] if len(pk_parts) >= 3 else item["PK"]

    return Api(
        api_key=api_key,
        owner_id=item["owner_id"],
        google_sheet_id=item["google_sheet_id"],
        refresh_token_info=RefreshTokenInfo(**item["refresh_token_info"]),
        frozen=item.get("frozen", False),
        cache_duration=item["cache_duration"],
        spreadsheet_title=item.get("spreadsheet_title"),  # Optional field
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(updated_stamp),
    )


def create_api(*, table: Table, api: Api) -> Api:
    """
    Create a new API in the db.

    Args:
        table: DynamoDB table resource (injected for testing)
        api: Api domain model to create

    Returns:
        Created API

    Raises:
        ConflictException: If API with this key already exists
    """
    item = to_item(api=api)

    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictException(f"API with key {api.api_key} already exists")
        raise

    return api


def update_api(
    *, table: Table, owner_id: str, api_id: str, updates: dict
) -> Api:
    """
    Update an existing API with partial updates.

    Args:
        table: DynamoDB table resource (injected for testing)
        owner_id: Owner account ID
        api_id: API key to update
        updates: Dictionary of fields to update

    Returns:
        Updated API

    Raises:
        NotFoundException: If API not found
    """
    # First, get the existing API
    existing_api = get_api(table=table, owner_id=owner_id, api_id=api_id)
    if existing_api is None:
        raise NotFoundException(f"API with key {api_id} not found")

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

    sheet_key = f"SHEET#{owner_id}#{api_id}"

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
            raise NotFoundException(f"API with key {api_id} not found")
        raise

    return from_item(item=response["Attributes"])


def delete_api(*, table: Table, owner_id: str, api_key: str) -> None:
    """
    Delete an API from the db.

    Args:
        table: DynamoDB table resource (injected for testing)
        owner_id: Owner account ID
        api_key: API key to delete

    Raises:
        NotFoundException: If API not found
    """
    sheet_key = f"SHEET#{owner_id}#{api_key}"
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
            raise NotFoundException(f"API with key {api_key} not found")
        raise


def get_api(*, table: Table, owner_id: str, api_id: str) -> Api | None:
    """
    Get an API by its key.

    Args:
        table: DynamoDB table resource
        owner_id: Owner account ID
        api_key: API key to retrieve

    Returns:
        Api if found, None otherwise
    """
    sheet_key = f"SHEET#{owner_id}#{api_id}"
    response = table.get_item(Key={"PK": sheet_key, "SK": sheet_key})
    item = response.get("Item", None)
    if item is None:
        return None
    return from_item(item=item)


def get_apis_by_owner(*, table: Table, owner_id: str) -> list[Api]:
    """
    Get all APIs owned by a specific account.

    Uses GSI2 with a filter to ensure only SHEET resources are returned,
    excluding other resource types that might belong to the same owner.
    """
    response = table.query(
        IndexName="GSI2",
        KeyConditionExpression="GSI2PK = :owner_pk",
        FilterExpression="begins_with(PK, :resource_type)",
        ExpressionAttributeValues={
            ":owner_pk": f"ACCOUNT#{owner_id}",
            ":resource_type": "SHEET#",
        },
    )

    items = response.get("Items", [])
    return [from_item(item=item) for item in items]


def get_api_by_google_sheet_id(
    *, table: Table, owner_id: str, google_sheet_id: str
) -> Api | None:
    """
    Find an API by Google Sheet ID for a specific owner.

    Queries all APIs for the owner via GSI2, then filters by google_sheet_id.
    This is performant because users typically have ~1-100 APIs max.

    Args:
        table: DynamoDB table resource
        owner_id: Account ID of the owner
        google_sheet_id: Google Sheet ID to search for

    Returns:
        Api if found, None otherwise
    """
    response = table.query(
        IndexName="GSI2",
        KeyConditionExpression="GSI2PK = :owner",
        FilterExpression="google_sheet_id = :sheet_id",
        ExpressionAttributeValues={
            ":owner": f"ACCOUNT#{owner_id}",
            ":sheet_id": google_sheet_id,
        },
    )

    items = response.get("Items", [])
    if not items:
        return None

    return from_item(item=items[0])
