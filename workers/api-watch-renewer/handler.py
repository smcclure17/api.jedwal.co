"""
Worker to renew Google Watch API subscriptions.

Google Drive Watch API expires every 24 hours. This lambda runs every ~12 hours
and renews any api watch channels expiring in the next 12 hours.
"""

from jedwal.apis import service as api_service
from jedwal.apis.notifications import service
from jedwal.apis.notifications.models import ApiWatchChannel
from jedwal.common.encryption import service as encryption_service
from jedwal.common.google_auth_fields import GoogleOauthFields
from jedwal.database.core import get_table

table = get_table()
encryption = encryption_service.get_encryption_service()


def handler(event, context):
    """Renew all watch channels expiring in the next 12 hours.

    This handler is triggered by EventBridge cron (every 12 hours).
    """

    expires_before = ApiWatchChannel.create_channel_expiration(hours=12)
    channels = service.get_soon_to_expire_channels(
        table=table, expires_before=expires_before
    )

    results = {
        "total": len(channels),
        "renewed": 0,
        "failed": 0,
        "errors": [],
    }

    for channel in channels:
        try:
            # Get API for OAuth credentials
            api = api_service.get_api(
                table=table, owner_id=channel.owner_id, api_id=channel.api_key
            )
            if not api:
                raise ValueError(f"API {channel.api_key} not found")

            # Refresh OAuth token
            auth = GoogleOauthFields.from_tokens(
                access_token="placeholder",
                refresh_token_info=api.refresh_token_info,
                encryption=encryption,
            )
            auth = auth.refresh_access_token()

            service.renew_watch_channel(
                table=table,
                channel=channel,
                auth=auth,
                new_expiration=ApiWatchChannel.create_channel_expiration(),
            )

            results["renewed"] += 1

        except Exception as e:
            results["failed"] += 1
            results["errors"].append(
                {
                    "channel_id": channel.channel_id,
                    "owner_id": channel.owner_id,
                    "api_key": channel.api_key,
                    "error": str(e),
                }
            )

    return results
