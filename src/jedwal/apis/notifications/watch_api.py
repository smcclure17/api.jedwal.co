import requests

from jedwal.config import settings


def register(
    *,
    bearer_token: str,
    google_drive_file_id: str,
    channel_id: str,
    expiration: int | None = None,
    callback_url=settings.api_watch_channel_callback_url,
    channel_token: str | None = None
):
    """Register a watch channel to start collecting notifications for a file"""
    response = requests.post(
        f"https://www.googleapis.com/drive/v3/files/{google_drive_file_id}/watch",
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        },
        json={
            "id": channel_id,
            "type": "webhook",
            "address": callback_url,
            "expiration": expiration,
            "token": channel_token
        },
    )
    response.raise_for_status()
    return response.json()


def stop(*, bearer_token: str, channel_id: str, resource_id: str):
    """Stop/kill a watch for a resource and channel"""
    response = requests.post(
        "https://www.googleapis.com/drive/v3/channels/stop",
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        },
        json={"id": channel_id, "resourceId": resource_id},
    )
    response.raise_for_status()
