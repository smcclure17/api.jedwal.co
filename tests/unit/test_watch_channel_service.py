"""Unit tests for watch channel service layer."""

import json
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from jedwal.apis.notifications import repository, service
from jedwal.apis.notifications.models import ApiWatchChannel
from jedwal.common.exceptions import BadRequestException

# We should think about injecting the SQS client or abstracting over it
# so we don't need to mock as much, but eh.
@patch("jedwal.apis.notifications.service.get_sqs_client")
def test_handle_watch_notification_success(mock_get_sqs_client, dynamodb_table):
    """Test successful webhook notification handling with matching token."""
    channel = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="test-channel-123",
        channel_token="secret-token-xyz",
        resource_id="google-resource-456",
        name="Test Channel",
        webhook_url="https://example.com/webhook",
        expires_at=int(time.time() * 1000) + 86400000,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.create(table=dynamodb_table, watch_channel=channel)

    # Mock SQS client
    mock_sqs = MagicMock()
    mock_get_sqs_client.return_value = mock_sqs

    # Call the service function with matching token
    service.handle_watch_notification(
        table=dynamodb_table,
        channel_id="test-channel-123",
        resource_state="update",
        resource_id="google-resource-456",
        channel_token="secret-token-xyz",  # Matches channel.channel_token
    )

    # Verify SQS message was sent
    mock_sqs.send_message.assert_called_once()
    call_args = mock_sqs.send_message.call_args

    # Verify message structure
    message_body = json.loads(call_args[1]["MessageBody"])
    assert message_body["webhookUrl"] == "https://example.com/webhook"
    assert message_body["method"] == "POST"
    assert message_body["retryCount"] == 0
    assert message_body["payload"]["event"] == "spreadsheet.update"
    assert message_body["payload"]["channel_id"] == "test-channel-123"
    assert message_body["payload"]["owner_id"] == "test-owner"
    assert message_body["payload"]["api_key"] == "test-api-key"


@patch("jedwal.apis.notifications.service.get_sqs_client")
def test_handle_watch_notification_token_mismatch(mock_get_sqs_client, dynamodb_table):
    """Test that webhook notification fails when token doesn't match."""
    # Create a channel in the database
    channel = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="test-channel-123",
        channel_token="secret-token-xyz",
        resource_id="google-resource-456",
        name="Test Channel",
        webhook_url="https://example.com/webhook",
        expires_at=int(time.time() * 1000) + 86400000,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.create(table=dynamodb_table, watch_channel=channel)

    # Mock SQS client (should not be called)
    mock_sqs = MagicMock()
    mock_get_sqs_client.return_value = mock_sqs

    # Call the service function with WRONG token
    with pytest.raises(BadRequestException) as exc_info:
        service.handle_watch_notification(
            table=dynamodb_table,
            channel_id="test-channel-123",
            resource_state="update",
            resource_id="google-resource-456",
            channel_token="wrong-token",  # Does NOT match channel.channel_token
        )

    # Verify exception message
    assert "Channel token did not match expected value" in str(exc_info.value)

    # Verify SQS message was NOT sent (security check failed)
    mock_sqs.send_message.assert_not_called()
