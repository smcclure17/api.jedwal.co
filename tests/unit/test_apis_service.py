"""Unit tests for APIs service layer."""

from unittest.mock import patch

from jedwal.apis import service


def test_generate_unique_api_key_retries_on_collision(dynamodb_table, sample_api):
    """Test that key generation retries if collision occurs."""
    # Create an API to cause a collision
    from jedwal.apis import repository

    repository.create_api(table=dynamodb_table, api=sample_api)

    # Mock randomname to return our existing key first, then a new one
    with patch("jedwal.apis.service.randomname.get_name") as mock_get_name:
        mock_get_name.side_effect = ["test-api-key", "new-unique-key"]

        key = service._generate_unique_api_key(
            table=dynamodb_table, owner_id="test-user-123"
        )

        # Should have called get_name twice (collision, then success)
        assert mock_get_name.call_count == 2
        assert key == "new-unique-key"


def test_extract_sheet_id_from_url():
    """Test extracting sheet ID from various URL formats."""
    # Full URL
    url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0"
    sheet_id = service._extract_sheet_id_from_url(url)
    assert sheet_id == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    # Just the ID
    just_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    sheet_id = service._extract_sheet_id_from_url(just_id)
    assert sheet_id == just_id


def test_get_api(dynamodb_table, sample_api):
    """Test retrieving an API by ID."""
    from jedwal.apis import repository

    # Create the API first
    repository.create_api(table=dynamodb_table, api=sample_api)

    # Retrieve it
    result = service.get_api(
        table=dynamodb_table, owner_id="test-user-123", api_id="test-api-key"
    )

    assert result is not None
    assert result.api_key == "test-api-key"
    assert result.owner_id == "test-user-123"


def test_update_api(dynamodb_table, sample_api):
    """Test updating an API with partial updates."""
    from jedwal.apis import repository
    from jedwal.apis.models import ApiUpdate

    # Create the API first
    repository.create_api(table=dynamodb_table, api=sample_api)

    # Update only frozen status
    updates = ApiUpdate(cache_duration=100)
    updated = service.update_api(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_id="test-api-key",
        updates=updates,
    )

    assert updated.cache_duration == 100  # Unchanged


def test_update_api_empty_updates(dynamodb_table, sample_api):
    """Test that empty updates just returns existing API."""
    from jedwal.apis import repository
    from jedwal.apis.models import ApiUpdate

    # Create the API first
    repository.create_api(table=dynamodb_table, api=sample_api)

    # Update with no changes
    updates = ApiUpdate()
    result = service.update_api(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_id="test-api-key",
        updates=updates,
    )

    assert result.api_key == "test-api-key"
    assert result.frozen is False


def test_delete_api(dynamodb_table, sample_api):
    """Test deleting an API."""
    from jedwal.apis import repository

    # Create the API first
    repository.create_api(table=dynamodb_table, api=sample_api)

    # Delete it
    service.delete_api(
        table=dynamodb_table, owner_id="test-user-123", api_id="test-api-key"
    )

    # Verify it's gone
    result = repository.get_api(
        table=dynamodb_table, owner_id="test-user-123", api_id="test-api-key"
    )
    assert result is None


def test_create_api_happy_path(dynamodb_table, sample_api_create, sample_account):
    """Test successful API creation with all validations passing."""
    from unittest.mock import Mock, patch

    from jedwal.account import repository as account_repository

    account_repository.create_account(table=dynamodb_table, account=sample_account)

    # We sadly need a lot of mocking here to interact with
    mock_spreadsheet = Mock()
    mock_spreadsheet.title = "Test Spreadsheet"
    mock_oauth_fields = Mock()
    mock_oauth_fields.google_oauth_creds = Mock()
    mock_gspread_client = Mock()

    with (
        patch(
            "jedwal.apis.service.google_sheets.open_spreadsheet",
            return_value=mock_spreadsheet,
        ),
        patch(
            "jedwal.apis.service.randomname.get_name", return_value="test-generated-key"
        ),
        patch(
            "jedwal.common.google_auth_fields.GoogleOauthFields.from_tokens",
            return_value=mock_oauth_fields,
        ),
        patch(
            "jedwal.apis.service.gspread.authorize", return_value=mock_gspread_client
        ),
    ):
        created_api = service.create_api(
            table=dynamodb_table,
            api_create=sample_api_create,
        )

        # Assert API was created successfully
        assert created_api.api_key == "test-generated-key"
        assert created_api.owner_id == "test-user-123"
        assert (
            created_api.google_sheet_id
            == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        )
        assert created_api.cache_duration == 3600
        assert created_api.frozen is False

        # Verify it's in the database
        from jedwal.apis import repository

        retrieved = repository.get_api(
            table=dynamodb_table,
            owner_id="test-user-123",
            api_id="test-generated-key",
        )
        assert retrieved is not None
        assert retrieved.api_key == "test-generated-key"
