import requests


WATCH_CENTRAL_CALLBACK_URL = "https://api.jedwal.co/notifications"


def register(
    *,
    bearer_token: str,
    google_drive_file_id: str,
    channel_id: str,
    expiration: int | None = None,
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
            "address": WATCH_CENTRAL_CALLBACK_URL,
            "expiration": expiration,
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
