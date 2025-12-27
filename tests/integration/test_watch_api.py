"""Integration tests for WatchApi class.

These tests interact with a real Google Sheet and require valid credentials.
"""

import time
import pytest

from jedwal.config import settings
from jedwal.account.models import RefreshTokenInfo
from jedwal.apis.notifications import watch_api
from jedwal.common.google_auth_fields import GoogleOauthFields

# This spreadsheet has already been selected/opened in the app on the account
# corresponding to test_data_refresh_info. If this were any random spreadsheet,
# the requests would fail as the credentials would not be able to read/see the file.
# test_data_refresh_info belongs to jedwal.testing.email@gmail.com
TEST_SHEET_ID = "1IyPUd8hmNC0VsB4aLfsiYSDPZi_XILoMvexQ-8sA_7U"
REFRESH_TOKEN_INFO = RefreshTokenInfo.from_dict_str(settings.test_data_refresh_info)


@pytest.mark.integration
def test_watch_api_e2e():
    """Test registering a watch channel on a real Google Sheet."""
    auth = GoogleOauthFields.from_tokens(
        access_token="Some token Value", refresh_token_info=REFRESH_TOKEN_INFO
    )
    auth = auth.refresh_access_token()

    # set very short expiration in case cleanup fails (10 seconds)
    expiration = int(time.time() * 1000) + (10 * 1000)
    channel_id_name = "my-jedwal-channel-api-test-1"

    response = watch_api.register(
        bearer_token=auth.access_token,
        google_drive_file_id=TEST_SHEET_ID,
        channel_id=channel_id_name,
        expiration=expiration,
        channel_token="some token",
        callback_url="https://example.com",
    )

    assert "id" in response
    assert response["id"] == channel_id_name

    watch_api.stop(
        bearer_token=auth.access_token,
        channel_id=channel_id_name,
        resource_id=response["resourceId"],
    )
