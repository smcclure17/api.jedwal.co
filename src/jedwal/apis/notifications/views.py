from fastapi import APIRouter, Request

from jedwal.account.models import AccountId
from jedwal.apis.models import ApiKey
from jedwal.apis.notifications import service
from jedwal.apis.notifications.models import ApiWatchChannelCreate, ApiWatchChannelRead
from jedwal.auth.service import VerifiedAccount
from jedwal.database.core import DbTable, SqSClient

authenticated_notifications_router = APIRouter(prefix="/notifications")
public_api_notifications_router = APIRouter(prefix="/notifications")


@authenticated_notifications_router.get("", response_model=list[ApiWatchChannelRead])
async def get_watch_channels(
    account_id: AccountId,
    api_id: ApiKey,
    table: DbTable,
):
    """Get all watch channels for an API"""
    channels = service.get_watch_channels(
        table=table, owner_id=account_id, api_key=api_id
    )
    return [ApiWatchChannelRead(**channel.model_dump()) for channel in channels]


@authenticated_notifications_router.post("", response_model=ApiWatchChannelRead)
async def create_watch_channel(
    account_id: AccountId,
    request: ApiWatchChannelCreate,
    table: DbTable,
    verified_account: VerifiedAccount,
):
    """Create or update a new watch channel for an API"""
    channel = service.create_watch_channel(
        table=table, watch_channel=request, account=verified_account
    )
    return ApiWatchChannelRead(**channel.model_dump())


@authenticated_notifications_router.delete("/{channel_id}")
async def delete_watch_channel(
    account_id: AccountId,
    api_id: ApiKey,
    channel_id: str,
    table: DbTable,
    verified_account: VerifiedAccount,
):
    service.delete_watch_channel(
        table=table,
        owner_id=account_id,
        api_key=api_id,
        channel_id=channel_id,
        account=verified_account,
    )


# If we change the path/signature for this make sure to update the
# "api_watch_channel_callback_url" config variable to match the new route.
@public_api_notifications_router.post("")
async def watch(table: DbTable, queue: SqSClient, request: Request):
    """Receive Google Drive watch notifications and fan out to user webhooks."""

    # Google sends channel info in headers
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    channel_token = request.headers.get("X-Goog-Channel-Token")

    service.handle_watch_notification(
        table=table,
        queue=queue,
        channel_id=channel_id,
        resource_state=resource_state or "unknown",
        resource_id=resource_id or "",
        channel_token=channel_token,
    )
    return {"ok": True}
