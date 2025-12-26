"""Google Drive Watch API expires every 24 hours.

This lambda runs every ~8 hours, looks for api watch channels expiring in the next 8 hours, and renews them

Renews by deleting the old record and re-creating a new one.
"""

import time

from jedwal.apis import service as api_service
from jedwal.apis.notifications import service
from jedwal.common.google_auth_fields import GoogleOauthFields
from jedwal.config import settings

from jedwal.database.core import get_table


table = get_table()


def handler(event, context):
    """Renew all watch channels expiring in the next 12 hours.

    This handler is triggered by EventBridge cron (daily).
    """

    # Get channels expiring in next 8 hours
    expires_before = int(time.time()) + (8 * 3600)
    channels = service.get_soon_to_expire_channels(
        table=table, expires_before=expires_before
    )

    results = {"total": len(channels), "renewed": 0, "failed": 0, "errors": []}

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
                access_token="placeholder", refresh_token_info=api.refresh_token_info
            )
            auth = auth.refresh_access_token()

            # Calculate new expiration (24 hours from now, in milliseconds)
            new_expiration = int(time.time() * 1000) + (24 * 3600 * 1000)
            service.renew_watch_channel(
                table=table,
                channel=channel,
                auth=auth,
                new_expiration=new_expiration,
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
