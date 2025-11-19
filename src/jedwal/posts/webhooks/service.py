import json
import logging
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from jedwal.config import settings
from jedwal.database.core import DbTable, get_sqs_client
from jedwal.posts.webhooks import repository
from jedwal.posts.webhooks.models import Webhook, WebhooksRead

logger = logging.getLogger(__name__)


def get_webhooks_for_post(*, table: DbTable, account_id: str, post_key: str):
    webhooks = repository.get_webhooks_for_post(
        table=table, account_id=account_id, post_key=post_key
    )

    if webhooks is None:
        return WebhooksRead(account_id=account_id, post_id=post_key, webhooks=[])

    return WebhooksRead(account_id=account_id, post_id=post_key, webhooks=webhooks)


def create_webhook_for_post(
    *, table: DbTable, account_id: str, post_key: str, webhook: Webhook
):
    webhook_read = get_webhooks_for_post(
        table=table, account_id=account_id, post_key=post_key
    )

    webhooks = webhook_read.webhooks + [webhook]
    repository.update_post_webhooks(
        table=table, account_id=account_id, post_key=post_key, webhooks=webhooks
    )


def delete_webhook_from_post(
    *, table: DbTable, account_id: str, post_key: str, webhook: Webhook
):
    webhook_read = get_webhooks_for_post(
        table=table, account_id=account_id, post_key=post_key
    )

    # For now, check uniqueness if name and url match. If this causes problems we
    # can add an ID or something.
    webhooks = []
    for w in webhook_read.webhooks:
        if w.url == webhook.url and w.name == webhook.name:
            continue
        webhooks.append(w)

    repository.update_post_webhooks(
        table=table, account_id=account_id, post_key=post_key, webhooks=webhooks
    )


def trigger_webhooks_for_post(*, table: DbTable, owner_id: str, post_id: str) -> int:
    """
    Trigger all webhooks for a specific document API.

    Args:
        owner_id: Owner of the document
        post_id: Name of the API
        event_data: Optional event data to include in webhook payload

    Returns:
        int: Number of webhooks successfully queued
    """
    try:
        post = get_webhooks_for_post(table=table, account_id=owner_id, post_key=post_id)
        webhooks = post.webhooks

        if not webhooks:
            return 0

        event_payload = {
            "event": "post.republished",
            "owner_id": owner_id,
            "post_id": post_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        successful_queues = 0

        for webhook in webhooks:
            success = _create_webhook_event(
                webhook_url=webhook.url,
                method=webhook.method,
                payload=event_payload,
                user_id=owner_id,
                post_id=post_id,
            )

            if success:
                successful_queues += 1

        logger.info(
            f"Queued {successful_queues}/{len(webhooks)} webhooks for {owner_id}/{post_id}"
        )
        return successful_queues

    except Exception as e:
        logger.error(f"Failed to trigger webhooks for {owner_id}/{post_id}: {str(e)}")
        return 0


def _create_webhook_event(
    webhook_url: str,
    method: str,
    payload: dict,
    user_id: str,
    post_id: str,
    retry_count: int = 0,
) -> bool:
    """Send a webhook event to the SQS queue for processing."""
    try:
        sqs = get_sqs_client()
        message_body = {
            "webhookUrl": webhook_url,
            "method": method,
            "payload": payload,
            "userId": user_id,
            "postId": post_id,
            "retryCount": retry_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = sqs.send_message(
            QueueUrl=settings.webhook_queue_url, MessageBody=json.dumps(message_body)
        )
        return True

    except ClientError as e:
        logger.error(f"Failed to queue webhook event: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error queuing webhook event: {str(e)}")
        return False
