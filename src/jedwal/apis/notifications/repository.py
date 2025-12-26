from datetime import datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import AccountId
from jedwal.apis.models import ApiKey
from jedwal.apis.notifications.models import ApiWatchChannel
from jedwal.common.exceptions import ConflictException, NotFoundException


def to_item(*, watch_channel: ApiWatchChannel) -> dict:
    """Convert domain model to DynamoDB item with keys."""
    # PK groups all channels for same API (without webhook hash)
    pk = f"API_WATCH_CHANNEL#{watch_channel.owner_id}#{watch_channel.api_key}"
    # SK differentiates by channel_id (which includes webhook hash)
    sk = f"CHANNEL#{watch_channel.channel_id}"
    return {
        "PK": pk,
        "SK": sk,
        "owner_id": watch_channel.owner_id,
        "api_key": watch_channel.api_key,
        "channel_id": watch_channel.channel_id,
        "resource_id": watch_channel.resource_id,
        "expires_at": watch_channel.expires_at,
        "webhook_url": watch_channel.webhook_url,
        "created_at": watch_channel.created_at.isoformat(),
        "updated_at": watch_channel.updated_at.isoformat(),
        "name": watch_channel.name,
        # for lookup by channel ID when webhook arrives
        "GSI1PK": f"CHANNEL_ID#{watch_channel.channel_id}",
        "GSI1SK": "METADATA",
        # for looking up all "expiring soon" items for renewal
        "GSI2PK": "API_WATCH_CHANNEL_EXPIRY",
        "GSI2SK": str(watch_channel.expires_at),  # Convert to string for GSI
    }


def from_item(*, item: dict) -> ApiWatchChannel:
    """Convert DynamoDB item to Worksheet domain model."""

    return ApiWatchChannel(
        owner_id=item["owner_id"],
        api_key=item["api_key"],
        channel_id=item["channel_id"],
        resource_id=item["resource_id"],
        webhook_url=item["webhook_url"],
        expires_at=item["expires_at"],
        name=item["name"],
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(item["updated_at"]),
    )


def create(*, table: Table, watch_channel: ApiWatchChannel):
    item = to_item(watch_channel=watch_channel)
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictException(
                f"Watch channel with key {watch_channel.api_key} already exists"
            ) from e
        raise
    return watch_channel


def read_by_channel_id(*, table: Table, channel_id: str) -> ApiWatchChannel | None:
    """Read a watch channel by channel_id (used when webhook arrives)"""
    response = table.query(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :pk",
        ExpressionAttributeValues={":pk": f"CHANNEL_ID#{channel_id}"},
    )

    items = response.get("Items", [])
    if not items:
        return None
    return from_item(item=items[0])


def list_channels_for_api(
    *, table: Table, owner_id: AccountId, api_key: ApiKey
) -> list[ApiWatchChannel]:
    """List all watch channels for a specific API"""
    response = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": f"API_WATCH_CHANNEL#{owner_id}#{api_key}",
            ":sk_prefix": "CHANNEL#",
        },
    )

    items = response.get("Items", [])
    return [from_item(item=item) for item in items]


def update(*, table: Table, watch_channel: ApiWatchChannel) -> ApiWatchChannel:
    """Update an existing watch channel. Fail if channel does not already exist"""
    watch_channel.updated_at = datetime.now()
    item = to_item(watch_channel=watch_channel)

    try:
        table.put_item(Item=item, ConditionExpression="attribute_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(
                f"Watch channel {watch_channel.channel_id} not found"
            ) from e
        raise
    return watch_channel


def delete(
    *, table: Table, owner_id: AccountId, api_key: ApiKey, channel_id: str
) -> None:
    """Delete an existing watch channel"""
    pk = f"API_WATCH_CHANNEL#{owner_id}#{api_key}"
    sk = f"CHANNEL#{channel_id}"
    try:
        table.delete_item(
            Key={"PK": pk, "SK": sk},
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(
                f"Watch channel {channel_id} for API {api_key} not found"
            ) from e
        raise


def get_soon_to_expire_channels(
    *, table: Table, expires_before: int
) -> list[ApiWatchChannel]:
    """Get all channels that will expire before the given timestamp"""
    response = table.query(
        IndexName="GSI2",
        KeyConditionExpression="GSI2PK = :pk AND GSI2SK < :expires_before",
        ExpressionAttributeValues={
            ":pk": "API_WATCH_CHANNEL_EXPIRY",
            ":expires_before": str(expires_before),  # Convert to string for comparison
        },
    )

    items = response.get("Items", [])
    return [from_item(item=item) for item in items]
