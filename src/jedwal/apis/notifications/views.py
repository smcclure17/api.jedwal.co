from fastapi import APIRouter, Request

from jedwal.account.models import AccountId
from jedwal.apis.models import ApiKey
from jedwal.apis.notifications import service
from jedwal.apis.notifications.models import ApiWatchChannel, ApiWatchChannelCreate
from jedwal.auth.service import VerifiedAccount
from jedwal.common.exceptions import ConflictException, NotFoundException
from jedwal.common.google_auth_fields import GoogleOauthFields
from jedwal.database.core import DbTable

authenticated_notifications_router = APIRouter(prefix="/notifications")
public_api_notifications_router = APIRouter(prefix="/notifications")


@authenticated_notifications_router.get("", response_model=list[ApiWatchChannel])
async def get_watch_channels(
    account_id: AccountId,
    api_id: ApiKey,
    table: DbTable,
):
    """Get all watch channels for an API"""
    channels = service.get_watch_channels(
        table=table, owner_id=account_id, api_key=api_id
    )
    return channels


@authenticated_notifications_router.post("", response_model=ApiWatchChannel)
async def create_watch_channel(
    account_id: AccountId,
    request: ApiWatchChannelCreate,
    table: DbTable,
    verified_account: VerifiedAccount,
):
    """Create or update a new watch channel for an API"""
    existing_channel = service.get_watch_channel(
        table=table,
        owner_id=account_id,
        api_key=request.api_key,
        webhook_url=request.webhook_url,
    )

    if existing_channel:
        raise ConflictException(detail="Watch channel already exists.")

    auth = GoogleOauthFields.from_tokens(
        access_token="SOME PLACEHOLDER TO FORCE REFRESH",
        refresh_token_info=verified_account.refresh_token_info,
    )
    auth = auth.refresh_access_token()
    return service.create_watch_channel(table=table, watch_channel=request, auth=auth)


@authenticated_notifications_router.delete("/{channel_id}")
async def delete_watch_channel(
    account_id: AccountId,
    api_id: ApiKey,
    channel_id: str,
    table: DbTable,
    verified_account: VerifiedAccount,
):
    auth = GoogleOauthFields.from_tokens(
        access_token="SOME PLACEHOLDER TO FORCE REFRESH",
        refresh_token_info=verified_account.refresh_token_info,
    )
    auth = auth.refresh_access_token()

    service.delete_watch_channel(
        table=table,
        owner_id=account_id,
        api_key=api_id,
        channel_id=channel_id,
        auth=auth,
    )


# If we change the path/signature for this make sure to update the
# "api_watch_channel_callback_url" config variable to match the new route.
@public_api_notifications_router.post("")
async def watch(table: DbTable, request: Request):
    """Receive Google Drive watch notifications and fan out to user webhooks."""

    # Google sends channel info in headers
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")
    resource_id = request.headers.get("X-Goog-Resource-ID")

    if not channel_id:
        raise NotFoundException("Channel not found.")

    service.handle_watch_notification(
        table=table,
        channel_id=channel_id,
        resource_state=resource_state or "unknown",
        resource_id=resource_id or "",
    )
    return {"ok": True}
