from datetime import UTC, datetime

from botocore.exceptions import ClientError

from jedwal.account.models import AccountId
from jedwal.common.exceptions import NotFoundException
from jedwal.database.core import Table
from jedwal.posts.models import PostKey
from jedwal.posts.webhooks.models import Webhook


def to_item(*, webhook: Webhook):
    return {
        "url": webhook.url,
        "method": webhook.method,
        "payload": webhook.payload,
        "name": webhook.name,
    }


def from_item(*, item: dict):
    return Webhook(
        url=item["url"],
        method=item["method"],
        payload=item["payload"],
        name=item["name"],
    )


def get_webhooks_for_post(*, table: Table, account_id: AccountId, post_key: PostKey):
    """Get a Post by its key with limited fields."""
    sheet_key = f"DOC#{account_id}#{post_key}"

    response = table.get_item(
        Key={"PK": sheet_key, "SK": sheet_key},
        ProjectionExpression="webhooks",
    )

    item = response.get("Item")
    if item is None:
        raise NotFoundException(detail=[{"msg": "Post not found"}])

    webhooks = item.get("webhooks")
    if webhooks is None:
        return None

    return [from_item(item=webhook) for webhook in webhooks]


def update_post_webhooks(
    *, table: Table, account_id: AccountId, post_key: PostKey, webhooks: list[Webhook]
):
    webhook_data = [to_item(webhook=webhook) for webhook in webhooks]

    post_pk = f"DOC#{account_id}#{post_key}"
    updated_at = datetime.now(tz=UTC).isoformat()

    try:
        table.update_item(
            Key={"PK": post_pk, "SK": post_pk},
            UpdateExpression="SET #webhooks = :webhooks, #updated_at = :updated_at",
            ExpressionAttributeNames={
                "#webhooks": "webhooks",
                "#updated_at": "updated_at",
            },
            ExpressionAttributeValues={
                ":webhooks": webhook_data,
                ":updated_at": updated_at,
            },
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(detail=[{"msg": "Post not found"}]) from e
        raise
