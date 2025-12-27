"""Integration tests for WatchApi class.

These tests interact with a real Google Sheet and require valid credentials.
"""

import time
import pytest
import requests

from jedwal.config import settings
from jedwal.apis.notifications import watch_api

# This spreadsheet has already been selected/opened in the app on the account
# corresponding to test_data_refresh_token. If this were any random spreadsheet,
# the requests would fail as the credentials would not be able to read/see the file.
# test_data_refresh_token belongs to jedwal.testing.email@gmail.com
TEST_SHEET_ID = "1IyPUd8hmNC0VsB4aLfsiYSDPZi_XILoMvexQ-8sA_7U"


def fetch_access_token_from_refresh_token():
    """Fetch an access token for our stored test refresh token."""

    print("TOKEN", settings.test_data_refresh_token[0:10])
    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": settings.test_data_refresh_token,
        "grant_type": "refresh_token",
    }
    response = requests.post("https://oauth2.googleapis.com/token", data=payload)
    print(response.status_code, response.text)
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.mark.integration
def test_watch_api_e2e():
    """Test registering a watch channel on a real Google Sheet."""
    access_token = fetch_access_token_from_refresh_token()

    # set very short expiration in case cleanup fails (10 seconds)
    expiration = int(time.time() * 1000) + (10 * 1000)
    channel_id_name = "my-jedwal-channel-api-test-2"

    response = watch_api.register(
        bearer_token=access_token,
        google_drive_file_id=TEST_SHEET_ID,
        channel_id=channel_id_name,
        expiration=expiration,
        channel_token="some token",
        callback_url="https://example.com",
    )

    assert "id" in response
    assert response["id"] == channel_id_name

    watch_api.stop(
        bearer_token=access_token,
        channel_id=channel_id_name,
        resource_id=response["resourceId"],
    )
