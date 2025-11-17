from fastapi import APIRouter

from jedwal.posts.webhooks import service
from jedwal.database.core import DbTable
from jedwal.posts.webhooks.models import Webhook, WebhookCreateRequest, WebhookDeleteRequest, WebhooksRead

authenticated_webhooks_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@authenticated_webhooks_router.get("", response_model=WebhooksRead)
async def get_webhooks(
    account_id: str,
    post_key: str,
    table: DbTable,
):
    return service.get_webhooks_for_post(
        table=table, account_id=account_id, post_key=post_key
    )


@authenticated_webhooks_router.post("", response_model=None)
async def create_webhook(
    account_id: str,
    post_key: str,
    webhook: WebhookCreateRequest,
    table: DbTable,
):
    return service.create_webhook_for_post(
        table=table, account_id=account_id, post_key=post_key, webhook=webhook
    )


@authenticated_webhooks_router.delete("", response_model=None)
async def create_webhook(
    account_id: str,
    post_key: str,
    webhook: WebhookDeleteRequest,
    table: DbTable,
):
    return service.delete_webhook_from_post(
        table=table, account_id=account_id, post_key=post_key, webhook=webhook
    )
