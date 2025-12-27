"""Unit tests for worksheets service layer."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import gspread
import pytest
from fastapi import HTTPException

from jedwal.apis.worksheets import repository, service
from jedwal.apis.worksheets.models import WorksheetCreate


def test_get_worksheet_data_cache_hit(
    dynamodb_table, sample_api, sample_worksheet_create, sample_passthrough_encryption
):
    """Test that get_worksheet_data returns cached data when cache is fresh."""
    # Save fresh worksheet to cache
    repository.save_worksheet(
        table=dynamodb_table, worksheet_create=sample_worksheet_create
    )

    # Mock Google Sheets (should NOT be called)
    mock_spreadsheet = Mock()
    with patch(
        "jedwal.apis.service.get_api_spreadsheet", return_value=mock_spreadsheet
    ):
        data, expires_at = service.get_worksheet_data(
            table=dynamodb_table,
            api=sample_api,
            worksheet_name="Sheet1",
            encryption=sample_passthrough_encryption,
        )

    # Should return cached data
    assert data == [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    assert expires_at == datetime(2030, 12, 31, 23, 59, 59, tzinfo=UTC)

    # Verify Google Sheets was NOT called
    mock_spreadsheet.worksheet.assert_not_called()


def test_get_worksheet_data_cache_miss(
    dynamodb_table, sample_api, sample_passthrough_encryption
):
    """Test that get_worksheet_data fetches from Google when cache is missing."""
    # Mock Google Sheets API
    mock_worksheet = Mock()
    mock_worksheet.get_all_records.return_value = [{"name": "Charlie", "age": 35}]

    mock_spreadsheet = Mock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    with patch(
        "jedwal.apis.service.get_api_spreadsheet", return_value=mock_spreadsheet
    ):
        data, expires_at = service.get_worksheet_data(
            table=dynamodb_table,
            api=sample_api,
            worksheet_name="Sheet1",
            encryption=sample_passthrough_encryption,
        )

    # Should return fresh data from Google
    assert data == [{"name": "Charlie", "age": 35}]

    # Should have cached it
    cached = repository.get_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
    )
    assert cached is not None
    assert cached.data == [{"name": "Charlie", "age": 35}]

    # Verify expiry is set correctly (api.cache_duration = 3600 seconds)
    now = datetime.now(UTC)
    expected_expiry = now + timedelta(seconds=3600)
    # Allow 5 second margin for test execution time
    assert abs((cached.expires_at - expected_expiry).total_seconds()) < 5


def test_get_worksheet_data_cache_expired(
    dynamodb_table, sample_api, sample_passthrough_encryption
):
    """Test that get_worksheet_data refetches when cache is expired."""
    # Save expired worksheet to cache
    expired_worksheet = WorksheetCreate(
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
        data=[{"name": "Old", "age": 1}],
        expires_at=datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC),
    )
    repository.save_worksheet(table=dynamodb_table, worksheet_create=expired_worksheet)

    # Mock Google Sheets API with new data
    mock_worksheet = Mock()
    mock_worksheet.get_all_records.return_value = [{"name": "Fresh", "age": 99}]

    mock_spreadsheet = Mock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    with patch(
        "jedwal.apis.service.get_api_spreadsheet", return_value=mock_spreadsheet
    ):
        data, expires_at = service.get_worksheet_data(
            table=dynamodb_table,
            api=sample_api,
            worksheet_name="Sheet1",
            encryption=sample_passthrough_encryption,
        )

    # Should return fresh data (not expired cache)
    assert data == [{"name": "Fresh", "age": 99}]

    # Verify cache was updated
    cached = repository.get_worksheet(
        table=dynamodb_table,
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
    )
    assert cached.data == [{"name": "Fresh", "age": 99}]
    assert not cached.is_expired


def test_get_worksheet_data_with_provided_spreadsheet(
    dynamodb_table, sample_api, sample_passthrough_encryption
):
    """Test passing a pre-fetched spreadsheet to avoid duplicate API calls."""
    # Mock worksheet
    mock_worksheet = Mock()
    mock_worksheet.get_all_records.return_value = [{"name": "Test", "age": 42}]

    # Mock spreadsheet
    mock_spreadsheet = Mock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    # Pass spreadsheet directly (should NOT call get_api_spreadsheet)
    with patch("jedwal.apis.service.get_api_spreadsheet") as mock_get_spreadsheet:
        data, expires_at = service.get_worksheet_data(
            table=dynamodb_table,
            api=sample_api,
            worksheet_name="Sheet1",
            spreadsheet=mock_spreadsheet,  # Pre-fetched
            encryption=sample_passthrough_encryption,
        )

    # Should use provided spreadsheet
    assert data == [{"name": "Test", "age": 42}]

    # Should NOT have called get_api_spreadsheet
    mock_get_spreadsheet.assert_not_called()


def test_get_worksheet_data_worksheet_not_found(
    dynamodb_table, sample_api, sample_passthrough_encryption
):
    """Test that WorksheetNotFound raises HTTP 404."""
    mock_spreadsheet = Mock()
    mock_spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound(
        "Not found"
    )

    with patch(
        "jedwal.apis.service.get_api_spreadsheet", return_value=mock_spreadsheet
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.get_worksheet_data(
                table=dynamodb_table,
                api=sample_api,
                worksheet_name="NonexistentSheet",
                encryption=sample_passthrough_encryption,
            )

    assert exc_info.value.status_code == 404
    assert "Worksheet not found" in str(exc_info.value.detail)


def test_get_worksheet_data_non_unique_columns(
    dynamodb_table, sample_api, sample_passthrough_encryption
):
    """Test that NonUniqueColumnsError raises HTTP 422."""
    from jedwal.apis import google_sheets

    mock_worksheet = Mock()
    mock_worksheet.get_all_records.side_effect = google_sheets.NonUniqueColumnsError(
        "Columns are not unique"
    )

    mock_spreadsheet = Mock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    with patch(
        "jedwal.apis.service.get_api_spreadsheet", return_value=mock_spreadsheet
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.get_worksheet_data(
                table=dynamodb_table,
                api=sample_api,
                worksheet_name="Sheet1",
                encryption=sample_passthrough_encryption,
            )

    assert exc_info.value.status_code == 422
    assert "Columns are not unique" in str(exc_info.value.detail)


def test_delete_all_worksheets_for_api(dynamodb_table, sample_api):
    """Test deleting all worksheets for an API."""
    # Create multiple worksheets
    for i in range(3):
        worksheet_create = WorksheetCreate(
            owner_id="test-user-123",
            api_key="test-api-key",
            title=f"Sheet{i + 1}",
            data=[{"row": i}],
            expires_at=datetime(2024, 12, 31, 23, 59, 59),
        )
        repository.save_worksheet(
            table=dynamodb_table, worksheet_create=worksheet_create
        )

    # Delete all
    count = service.delete_all_worksheets_for_api(
        table=dynamodb_table, owner_id="test-user-123", api_key="test-api-key"
    )

    assert count == 3

    # Verify they're gone
    worksheets = repository.get_all_worksheets_for_api(
        table=dynamodb_table, owner_id="test-user-123", api_key="test-api-key"
    )
    assert len(worksheets) == 0
