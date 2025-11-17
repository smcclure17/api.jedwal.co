from jedwal.database.core import DbTable
from jedwal.posts.webhooks import repository
from jedwal.posts.webhooks.models import Webhook, WebhooksRead


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
