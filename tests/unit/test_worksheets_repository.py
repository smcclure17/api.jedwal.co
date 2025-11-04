"""Unit tests for worksheets repository layer."""

from datetime import datetime, timezone

from jedwal.apis.worksheets import repository
from jedwal.apis.worksheets.models import WorksheetCreate


def test_save_and_get_worksheet(dynamodb_table, sample_worksheet_create):
    """Test saving and retrieving a worksheet from cache."""
    # Save worksheet
    saved = repository.save_worksheet(
        table=dynamodb_table, worksheet_create=sample_worksheet_create
    )

    assert saved.owner_id == "test-user-123"
    assert saved.api_key == "test-api-key"
    assert saved.title == "Sheet1"
    assert len(saved.data) == 2
    assert saved.data[0]["name"] == "Alice"

    # Retrieve it
    retrieved = repository.get_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
    )

    assert retrieved is not None
    assert retrieved.owner_id == "test-user-123"
    assert retrieved.title == "Sheet1"
    assert retrieved.data == saved.data
    assert retrieved.expires_at == saved.expires_at


def test_get_nonexistent_worksheet(dynamodb_table):
    """Test getting a worksheet that doesn't exist returns None."""
    result = repository.get_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="nonexistent",
        title="Sheet1",
    )

    assert result is None


def test_save_worksheet_upserts(dynamodb_table, sample_worksheet_create):
    """Test that saving a worksheet with same key replaces the old one."""
    # Save first version
    first = repository.save_worksheet(
        table=dynamodb_table, worksheet_create=sample_worksheet_create
    )

    # Save updated version with new data
    updated_create = WorksheetCreate(
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
        data=[{"name": "Charlie", "age": 35}],
        expires_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    second = repository.save_worksheet(
        table=dynamodb_table, worksheet_create=updated_create
    )

    # Retrieve - should get the updated version
    retrieved = repository.get_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
    )

    assert retrieved is not None
    assert len(retrieved.data) == 1
    assert retrieved.data[0]["name"] == "Charlie"
    assert retrieved.expires_at.year == 2025


def test_get_all_worksheets_for_api(dynamodb_table):
    """Test retrieving all worksheets for a specific API."""
    # Create multiple worksheets for the same API
    for i in range(3):
        worksheet_create = WorksheetCreate(
            owner_id="test-user-123",
            api_key="test-api-key",
            title=f"Sheet{i+1}",
            data=[{"row": i}],
            expires_at=datetime(2024, 12, 31, 23, 59, 59),
        )
        repository.save_worksheet(table=dynamodb_table, worksheet_create=worksheet_create)

    # Create a worksheet for a different API
    other_worksheet = WorksheetCreate(
        owner_id="test-user-123",
        api_key="other-api-key",
        title="OtherSheet",
        data=[{"row": 99}],
        expires_at=datetime(2024, 12, 31, 23, 59, 59),
    )
    repository.save_worksheet(table=dynamodb_table, worksheet_create=other_worksheet)

    # Get all worksheets for test-api-key
    worksheets = repository.get_all_worksheets_for_api(
        table=dynamodb_table, owner_id="test-user-123", api_key="test-api-key"
    )

    assert len(worksheets) == 3
    titles = {ws.title for ws in worksheets}
    assert titles == {"Sheet1", "Sheet2", "Sheet3"}


def test_delete_worksheet(dynamodb_table, sample_worksheet_create):
    """Test deleting a specific worksheet."""
    # Save worksheet
    repository.save_worksheet(table=dynamodb_table, worksheet_create=sample_worksheet_create)

    # Verify it exists
    result = repository.get_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
    )
    assert result is not None

    # Delete it
    repository.delete_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
    )

    # Verify it's gone
    result = repository.get_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
    )
    assert result is None


def test_delete_worksheet_idempotent(dynamodb_table):
    """Test that deleting a nonexistent worksheet doesn't raise an error."""
    # Should not raise
    repository.delete_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="nonexistent",
        title="Sheet1",
    )


def test_delete_all_worksheets_for_api(dynamodb_table):
    """Test deleting all worksheets for an API."""
    # Create multiple worksheets for the same API
    for i in range(3):
        worksheet_create = WorksheetCreate(
            owner_id="test-user-123",
            api_key="test-api-key",
            title=f"Sheet{i+1}",
            data=[{"row": i}],
            expires_at=datetime(2024, 12, 31, 23, 59, 59),
        )
        repository.save_worksheet(table=dynamodb_table, worksheet_create=worksheet_create)

    # Create a worksheet for a different API
    other_worksheet = WorksheetCreate(
        owner_id="test-user-123",
        api_key="other-api-key",
        title="OtherSheet",
        data=[{"row": 99}],
        expires_at=datetime(2024, 12, 31, 23, 59, 59),
    )
    repository.save_worksheet(table=dynamodb_table, worksheet_create=other_worksheet)

    # Delete all worksheets for test-api-key
    deleted_count = repository.delete_all_worksheets_for_api(
        table=dynamodb_table, owner_id="test-user-123", api_key="test-api-key"
    )

    assert deleted_count == 3

    # Verify they're gone
    worksheets = repository.get_all_worksheets_for_api(
        table=dynamodb_table, owner_id="test-user-123", api_key="test-api-key"
    )
    assert len(worksheets) == 0

    # Verify other API's worksheets are still there
    other_worksheets = repository.get_all_worksheets_for_api(
        table=dynamodb_table, owner_id="test-user-123", api_key="other-api-key"
    )
    assert len(other_worksheets) == 1
    assert other_worksheets[0].title == "OtherSheet"


def test_worksheet_is_expired_property(sample_worksheet):
    """Test the is_expired property on Worksheet model."""
    # Past expiry
    past_worksheet = sample_worksheet.model_copy(
        update={"expires_at": datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)}
    )
    assert past_worksheet.is_expired is True

    # Future expiry
    future_worksheet = sample_worksheet.model_copy(
        update={"expires_at": datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)}
    )
    assert future_worksheet.is_expired is False
