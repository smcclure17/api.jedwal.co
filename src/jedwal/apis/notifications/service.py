import json
import time
from datetime import UTC, datetime

from jedwal.account.models import AccountId
from jedwal.apis import service as apis_service
from jedwal.apis.models import ApiKey
from jedwal.apis.notifications import repository, watch_api
from jedwal.apis.notifications.models import ApiWatchChannel, ApiWatchChannelCreate
from jedwal.common.exceptions import NotFoundException
from jedwal.common.google_auth_fields import GoogleOauthFields
from jedwal.config import settings
from jedwal.database.core import DbTable, get_sqs_client


def get_watch_channels(*, table: DbTable, owner_id: AccountId, api_key: ApiKey):
    return repository.list_channels_for_api(
        table=table, owner_id=owner_id, api_key=api_key
    )


def get_watch_channel(
    *, table: DbTable, owner_id: AccountId, api_key: ApiKey, webhook_url: str
) -> ApiWatchChannel | None:
    channel_id = ApiWatchChannel.create_channel_id(
        owner_id=owner_id, api_key=api_key, webhook_url=webhook_url
    )
    return repository.read_by_channel_id(table=table, channel_id=channel_id)


def create_watch_channel(
    *, table: DbTable, watch_channel: ApiWatchChannelCreate, auth: GoogleOauthFields
):
    channel_id = ApiWatchChannel.create_channel_id(
        owner_id=watch_channel.owner_id,
        api_key=watch_channel.api_key,
        webhook_url=watch_channel.webhook_url,
    )

    api = apis_service.get_api(
        table=table, owner_id=watch_channel.owner_id, api_id=watch_channel.api_key
    )

    if api is None:
        raise NotFoundException(detail="Could not find API to create notifications for")

    expiration = int(time.time() * 1000) + (24 * 3600 * 1000)
    google_channel = watch_api.register(
        bearer_token=auth.access_token,
        google_drive_file_id=api.google_sheet_id,
        channel_id=channel_id,
        expiration=expiration,
    )

    try:
        watch_channel_final = ApiWatchChannel(
            channel_id=channel_id,
            owner_id=watch_channel.owner_id,
            api_key=watch_channel.api_key,
            name=watch_channel.name,
            expires_at=google_channel["expiration"],  # check this
            resource_id=google_channel["resourceId"],
            webhook_url=watch_channel.webhook_url,
        )

        watch_channel = repository.create(
            table=table, watch_channel=watch_channel_final
        )
        return watch_channel_final
    except Exception as e:
        # rollback watch api registry if persisting fails
        watch_api.stop(
            bearer_token=auth.access_token,
            channel_id=channel_id,
            resource_id=google_channel["resourceId"],
        )
        raise e


def read_by_channel_id(*, table: DbTable, channel_id: str):
    return repository.read_by_channel_id(table=table, channel_id=channel_id)


def delete_watch_channel(
    *,
    table: DbTable,
    owner_id: AccountId,
    api_key: ApiKey,
    channel_id: str,
    auth: GoogleOauthFields,
):
    watch_channel = read_by_channel_id(table=table, channel_id=channel_id)
    if watch_channel is None:
        raise NotFoundException("Could not find watch channel to delete")

    watch_api.stop(
        bearer_token=auth.access_token,
        channel_id=channel_id,
        resource_id=watch_channel.resource_id,
    )

    repository.delete(
        table=table, owner_id=owner_id, api_key=api_key, channel_id=channel_id
    )


def renew_watch_channel(
    *,
    table: DbTable,
    channel: ApiWatchChannel,
    auth: GoogleOauthFields,
    new_expiration: int,
) -> ApiWatchChannel:
    """Renew a watch channel by extending its expiration."""

    watch_api.stop(
        bearer_token=auth.access_token,
        channel_id=channel.channel_id,
        resource_id=channel.resource_id,
    )

    # Get API for google_sheet_id
    api = apis_service.get_api(
        table=table, owner_id=channel.owner_id, api_id=channel.api_key
    )
    if not api:
        raise NotFoundException(f"API {channel.api_key} not found")

    response = watch_api.register(
        bearer_token=auth.access_token,
        google_drive_file_id=api.google_sheet_id,
        channel_id=channel.channel_id,
        expiration=new_expiration,
    )

    # Update channel with new expiration and resource_id
    channel.expires_at = new_expiration
    channel.resource_id = response["resourceId"]
    return repository.update(table=table, watch_channel=channel)


def get_soon_to_expire_channels(*, table: DbTable, expires_before: int):
    return repository.get_soon_to_expire_channels(
        table=table, expires_before=expires_before
    )


def handle_watch_notification(
    *, table: DbTable, channel_id: str, resource_state: str, resource_id: str
):
    """Handle incoming Google Drive watch notification and fan out to user webhook."""

    if resource_state == "sync":
        return  # skip initial registration message

    channel = repository.read_by_channel_id(table=table, channel_id=channel_id)
    if not channel:
        raise NotFoundException("Channel to notify not found")

    payload = {
        "event": f"spreadsheet.{resource_state}",
        "channel_id": channel_id,
        "resource_id": resource_id,
        "resource_state": resource_state,
        "owner_id": channel.owner_id,
        "api_key": channel.api_key,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    sqs = get_sqs_client()
    message_body = {
        "webhookUrl": channel.webhook_url,
        "method": "POST",
        "payload": payload,
        "retryCount": 0,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    sqs.send_message(
        QueueUrl=settings.webhook_queue_url, MessageBody=json.dumps(message_body)
    )
