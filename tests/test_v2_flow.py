from datetime import datetime, timedelta, timezone
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sheetsapi import config, email_client, user_helpers
from sheetsapi.account_repo import (
    AccountRepo,
    OrganizationNotFoundError,
    UserAlreadyExistsError,
)
from sheetsapi.rate_limiter import RateLimitRepo, RateLimitExceededError
from sheetsapi.sheet_repo import SheetApiRepo

config.Config.init()

from sheetsapi.models.domain_models import RefreshTokenInfo, UserSession

from app import app
from dependencies import get_current_user


# Test constants
EMAIL = "jedwal.testing.email@gmail.com"
USER_ID = "105494633096025495775"
TEST_SHEET_ID = "1fmaTbMZiD8VmgR27DbxO8twpyQybVsMVv5yKLoPhBWU"
REFRESH_TOKEN_INFO = RefreshTokenInfo.from_dict_str(
    config.Config.Constants.TEST_DATA_REFRESH_INFO
)

account_repo = AccountRepo.from_table_name()
sheet_repo = SheetApiRepo.from_table_name()


def test_end_to_end_api_flow_v2():
    """Test the complete API flow with the v2 repo and endpoints."""
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _skip_auth_and_mock_user

    # Test loading account data
    response = client.get(f"/get-account-data")
    assert (
        response.status_code == 200
    ), f"Getting account data failed: {response.json()}"

    # Test API creation with new endpoints
    response = client.post(
        "/create-api", data={"google_sheet_id": TEST_SHEET_ID, "owner_id": USER_ID}
    )
    assert response.status_code == 200, f"Creating API failed: {response.json()}"
    api_name = response.json()["api_name"]

    # Test API creation, API already exists
    response = client.post(
        "/create-api", data={"google_sheet_id": TEST_SHEET_ID, "owner_id": USER_ID}
    )
    assert response.status_code == 200, f"Creating duplicate API failed"
    assert response.json()["api_name"] == api_name, "Names don't match"

    # Test get all sheets
    response = client.get(f"/get-all-sheets/{USER_ID}")
    assert response.status_code == 200, f"Getting user sheets failed: {response.json()}"
    assert (
        len([s for s in response.json()["results"] if s["sheet_api_name"] == api_name])
        == 1
    )

    # Test API access with new URL pattern
    response = client.get(f"/api/{USER_ID}/{api_name}")
    assert response.status_code == 200, f"Getting API data failed: {response.json()}"

    # Test updating cache duration
    response = client.post(
        "/update-cache-duration",
        json={"owner_id": USER_ID, "sheet_api_name": api_name, "cache_duration": 101},
    )
    assert response.status_code == 200, "Update cache duration failed."

    # Verify cache duration was updated
    sheets = client.get(f"/get-all-sheets/{USER_ID}").json()["results"]
    assert [s for s in sheets if s["sheet_api_name"] == api_name][0][
        "cache_duration"
    ] == 101

    # Test API deletion with new URL pattern
    response = client.delete(f"/delete-api/{USER_ID}/{api_name}")
    assert response.status_code == 200, f"Delete failed: {response.json()}"

    # Verify the API was deleted
    response = client.get(f"/api/{USER_ID}/{api_name}")
    assert response.status_code == 404, "API should return 404 after deletion"

    # Clean up, so the override doesn't affect other tests
    app.dependency_overrides[get_current_user] = get_current_user


def test_end_to_end_orgs_v2():
    """Test organization operations with the v2 repo and endpoints."""
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _skip_auth_and_mock_user

    # Ensure user account exists first (could be done in setup)
    try:
        account_repo.create_user(
            user_id=USER_ID,
            email=EMAIL,
            refresh_token_info=REFRESH_TOKEN_INFO,
            given_name="Jedwal",
            family_name="Tester",
            account_status="premium",  # Start as premium to create org
        )
    except UserAlreadyExistsError:
        # User already exists, update to premium status
        account_repo.update_account(USER_ID, {"account_status": "premium"})

    # Test create org
    response = client.post(
        "/create-organization", json={"name": "test-org-v2", "invitees": []}
    )
    assert (
        response.status_code == 200
    ), f"Creating organization failed: {response.json()}"
    org_id = response.json()["id"]

    # Test newly created org exists
    response = client.get(f"/get-account-data?account_id={org_id}")
    assert (
        response.status_code == 200
    ), f"Getting organization failed: {response.json()}"
    assert response.json()["id"] == org_id

    # Test list user orgs
    response = client.get(f"/get-account-data?account_id={USER_ID}")
    assert (
        response.status_code == 200
    ), f"Getting organizations failed: {response.json()}"
    res = response.json()["orgs"]
    assert len([org for org in res if org["account_id"] == org_id]) == 1

    # Test create API as org
    response = client.post(
        "/create-api", data={"google_sheet_id": TEST_SHEET_ID, "owner_id": org_id}
    )
    assert (
        response.status_code == 200
    ), f"Creating API for org failed: {response.json()}"
    api_name = response.json()["api_name"]

    # Test org API does not show up in personal sheets
    response = client.get(f"/get-all-sheets/{USER_ID}")
    assert response.status_code == 200
    assert (
        len([s for s in response.json()["results"] if s["sheet_api_name"] == api_name])
        == 0
    )

    # Test org sheets are visible in org sheets endpoint
    response = client.get(f"/get-all-sheets/{org_id}")
    assert response.status_code == 200
    assert (
        len([s for s in response.json()["results"] if s["sheet_api_name"] == api_name])
        == 1
    )

    # Test API access for org-owned sheet
    response = client.get(f"/api/{org_id}/{api_name}")
    assert response.status_code == 200

    # Test delete org API
    response = client.delete(f"/delete-api/{org_id}/{api_name}")
    assert response.status_code == 200

    # Test delete org
    response = client.delete(f"/organization/{org_id}")
    assert response.status_code == 200

    # Cleanup
    try:
        account_repo.delete_organization(org_id)
    except OrganizationNotFoundError:
        pass  # Already deleted

    # Clean up, so the override doesn't affect other tests
    app.dependency_overrides[get_current_user] = get_current_user


def test_account_status_v2():
    """Test premium/free status features."""
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _skip_auth_and_mock_user

    # Ensure user exists as premium to start
    try:
        account_repo.create_user(
            user_id=USER_ID,
            email=EMAIL,
            refresh_token_info=REFRESH_TOKEN_INFO,
            given_name="Test",
            family_name="User",
            account_status="premium",
        )
    except UserAlreadyExistsError:
        # User exists, update to premium
        account_repo.update_account(USER_ID, {"account_status": "premium"})

    # Create three test APIs
    test_sheets = [
        "18BGpFOXi11rin6mz3R9W5KrJWuN5x1jQ92H7UA_pzRE",
        TEST_SHEET_ID,
        "10urNaF0yFgn0KAzQGI7DCdEbZZsEsDsaVX7_Nq6WrLI",
    ]
    api_names = []
    for test_sheet in test_sheets:
        response = client.post(
            "/create-api", data={"google_sheet_id": test_sheet, "owner_id": USER_ID}
        )
        assert response.status_code == 200
        api_names.append(response.json()["api_name"])

    # Test all APIs are accessible when premium
    for name in api_names:
        response = client.get(f"/api/{USER_ID}/{name}")
        assert response.status_code == 200, f"failed /api/{USER_ID}/{name}"

    # Downgrade account to free
    result = account_repo.downgrade_account(USER_ID)
    assert result["new_status"] == "free"
    assert result["sheets_frozen"] == 1  # One API should be frozen

    # Get the sheets to see which ones are actually frozen
    sheets = sheet_repo.get_apis_for_account(USER_ID)
    sheet_status = {
        sheet["sheet_api_name"]: sheet.get("frozen", False) for sheet in sheets
    }

    print(f"Sheet freeze status: {sheet_status}")

    # Verify two sheets are active and one is frozen
    active_sheets = [name for name, frozen in sheet_status.items() if not frozen]
    frozen_sheets = [name for name, frozen in sheet_status.items() if frozen]

    assert (
        len(active_sheets) == 2
    ), f"Expected 2 active sheets, got {len(active_sheets)}"
    assert len(frozen_sheets) == 1, f"Expected 1 frozen sheet, got {len(frozen_sheets)}"

    # Check active APIs work
    for name in active_sheets:
        response = client.get(f"/api/{USER_ID}/{name}")
        assert response.status_code == 200, f"Active API {name} should return 200"

    # Check frozen API is restricted
    for name in frozen_sheets:
        response = client.get(f"/api/{USER_ID}/{name}")
        assert response.status_code == 401, f"Frozen API {name} should return 401"

    # Upgrade back to premium
    result = account_repo.upgrade_account(USER_ID)
    assert result["new_status"] == "premium"

    # All APIs should work again
    for name in api_names:
        response = client.get(f"/api/{USER_ID}/{name}")
        assert response.status_code == 200

    # Clean up APIs
    for name in api_names:
        client.delete(f"/delete-api/{USER_ID}/{name}")

    # Clean up, so the override doesn't affect other tests
    app.dependency_overrides[get_current_user] = get_current_user


def _skip_auth_and_mock_user():
    """Returns a mock user session for testing."""
    return UserSession(
        iss="https://accounts.google.com",
        azp="293432620407-osstrkdh0garuvogej84muq2tcbu35bk.apps.googleusercontent.com",
        aud="293432620407-osstrkdh0garuvogej84muq2tcbu35bk.apps.googleusercontent.com",
        sub=USER_ID,  # Use test user ID
        email=EMAIL,  # Use test email
        email_verified=True,
        at_hash="hashed-at-value",
        nonce="random-nonce-value",
        name="Test User",
        picture="https://example.com/profile.jpg",
        given_name="Jedwal",
        family_name="Tester",
        iat=int(datetime.now().timestamp()),
        exp=int((datetime.now() + timedelta(hours=1)).timestamp()),
        access_token="test-access-token",
    )


def test_rate_limit_functionality():
    """Test the rate limiting functionality using the live DynamoDB."""
    # Use a unique identifier for this test run to avoid conflicts
    test_id = f"test-{int(time.time())}"
    resource_type = "TEST"
    resource_id = f"{test_id}-resource"

    # Use low limits for testing
    test_limit = 3

    # Create repo instance
    repo = RateLimitRepo.from_table_name()

    # Get current timestamp for verification later
    now = datetime.now(timezone.utc)
    timestamp_day = now.strftime("%Y-%m-%d")

    print(f"Testing rate limit at time: {timestamp_day} for resource: {resource_id}")

    # Test incrementing under the limit
    for i in range(1, test_limit + 1):
        is_exceeded, count = repo.check_rate_limit(
            resource_type=resource_type, resource_id=resource_id, limit=test_limit
        )
        assert is_exceeded is False, f"Should not exceed limit at count {i}"
        assert count <= i, f"Count should be at most {i}, got {count}"

    # One more request should exceed the limit
    try:
        is_exceeded, count = repo.check_rate_limit(
            resource_type=resource_type, resource_id=resource_id, limit=test_limit
        )
        # If we get here, the rate limit wasn't enforced
        assert False, "Should have raised RateLimitExceededError"
    except RateLimitExceededError as e:
        # Verify error details
        assert e.resource_type == resource_type
        assert e.resource_id == resource_id
        assert e.limit == test_limit
        assert e.reset_time is not None, "Reset time should be provided"

    # Verify we can retrieve the rate limit counts
    counts = repo.get_rate_limit_counts(
        resource_type=resource_type, resource_id=resource_id
    )

    # We should have at least one record
    assert len(counts) >= 1, "Should have at least one rate limit record"

    # The current timestamp should have the count we expect
    current_count = counts.get(timestamp_day, 0)
    assert (
        current_count >= test_limit
    ), f"Count for {timestamp_day} should be at least {test_limit}"
