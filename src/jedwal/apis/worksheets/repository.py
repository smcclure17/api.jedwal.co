from datetime import datetime

from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import AccountId
from jedwal.apis.models import ApiKey
from jedwal.apis.worksheets.models import Worksheet, WorksheetCreate


def to_item(*, worksheet: Worksheet) -> dict:
    """Convert domain model to DynamoDB item with keys."""
    # PK format: SHEET#{owner_id}#{api_key}
    # SK format: WS#{title}
    sheet_key = f"SHEET#{worksheet.owner_id}#{worksheet.api_key}"
    ws_key = f"WS#{worksheet.title}"

    return {
        "PK": sheet_key,
        "SK": ws_key,
        "owner_id": worksheet.owner_id,
        "api_key": worksheet.api_key,
        "title": worksheet.title,
        "data": worksheet.data,
        "expires_at": worksheet.expires_at.isoformat(),
        "created_at": worksheet.created_at.isoformat(),
        "updated_at": worksheet.updated_at.isoformat(),
    }


def from_item(*, item: dict) -> Worksheet:
    """Convert DynamoDB item to Worksheet domain model."""
    # updated_at might not exist in db, so just set it if not
    updated_stamp = item.get("updated_at", datetime.now().isoformat())

    return Worksheet(
        owner_id=item["owner_id"],
        api_key=item["api_key"],
        title=item["title"],
        data=item["data"],
        expires_at=datetime.fromisoformat(item["expires_at"]),
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(updated_stamp),
    )


def save_worksheet(*, table: Table, worksheet_create: WorksheetCreate) -> Worksheet:
    """
    Save (create or replace) a worksheet cache entry.

    Args:
        table: DynamoDB table resource
        worksheet_create: WorksheetCreate schema with data to save

    Returns:
        Created/updated Worksheet
    """
    worksheet = Worksheet(
        owner_id=worksheet_create.owner_id,
        api_key=worksheet_create.api_key,
        title=worksheet_create.title,
        data=worksheet_create.data,
        expires_at=worksheet_create.expires_at,
    )

    item = to_item(worksheet=worksheet)
    table.put_item(Item=item)

    return worksheet


def get_worksheet(
    *, table: Table, owner_id: AccountId, api_key: ApiKey, title: str
) -> Worksheet | None:
    """
    Get a cached worksheet by its title.

    Args:
        table: DynamoDB table resource
        owner_id: Owner account ID
        api_key: API key
        title: Worksheet title

    Returns:
        Worksheet if found, None otherwise
    """
    sheet_key = f"SHEET#{owner_id}#{api_key}"
    ws_key = f"WS#{title}"

    response = table.get_item(Key={"PK": sheet_key, "SK": ws_key})
    item = response.get("Item", None)

    if item is None:
        return None

    return from_item(item=item)


def get_all_worksheets_for_api(
    *, table: Table, owner_id: AccountId, api_key: ApiKey
) -> list[Worksheet]:
    """
    Get all cached worksheets for a specific API.

    Args:
        table: DynamoDB table resource
        owner_id: Owner account ID
        api_key: API key

    Returns:
        List of Worksheet objects (may be empty)
    """
    sheet_key = f"SHEET#{owner_id}#{api_key}"

    response = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": sheet_key,
            ":sk_prefix": "WS#",
        },
    )

    items = response.get("Items", [])
    return [from_item(item=item) for item in items]


def delete_worksheet(*, table: Table, owner_id: AccountId, api_key: ApiKey, title: str) -> None:
    """
    Delete a specific worksheet cache entry.

    Args:
        table: DynamoDB table resource
        owner_id: Owner account ID
        api_key: API key
        title: Worksheet title

    Note: Does not raise exception if worksheet doesn't exist (idempotent)
    """
    sheet_key = f"SHEET#{owner_id}#{api_key}"
    ws_key = f"WS#{title}"

    table.delete_item(Key={"PK": sheet_key, "SK": ws_key})


def delete_all_worksheets_for_api(*, table: Table, owner_id: AccountId, api_key: ApiKey) -> int:
    """Delete all cached worksheets for a specific API."""

    sheet_key = f"SHEET#{owner_id}#{api_key}"
    worksheets = get_all_worksheets_for_api(
        table=table, owner_id=owner_id, api_key=api_key
    )

    with table.batch_writer() as batch:
        for worksheet in worksheets:
            ws_key = f"WS#{worksheet.title}"
            batch.delete_item(Key={"PK": sheet_key, "SK": ws_key})

    return len(worksheets)
