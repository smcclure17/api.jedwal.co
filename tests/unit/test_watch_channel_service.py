"""Unit tests for watch channel service layer."""

import json
import time

import pytest

from jedwal.apis.notifications import repository, service
from jedwal.apis.notifications.models import ApiWatchChannel
from jedwal.common.exceptions import BadRequestException
from jedwal.config import settings


def test_handle_watch_notification_success(dynamodb_table, sqs_client):
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
    )
    repository.create(table=dynamodb_table, watch_channel=channel)

    # Call the service function with matching token
    service.handle_watch_notification(
        table=dynamodb_table,
        queue=sqs_client,
        channel_id="test-channel-123",
        resource_state="update",
        resource_id="google-resource-456",
        channel_token="secret-token-xyz",  # Matches channel.channel_token
    )

    messages = sqs_client.receive_message(
        QueueUrl=settings.webhook_queue_url, MaxNumberOfMessages=1
    )

    assert "Messages" in messages
    message_body = json.loads(messages["Messages"][0]["Body"])
    assert message_body["webhookUrl"] == "https://example.com/webhook"
    assert message_body["method"] == "POST"
    assert message_body["retryCount"] == 0
    assert message_body["payload"]["event"] == "spreadsheet.update"
    assert message_body["payload"]["channel_id"] == "test-channel-123"
    assert message_body["payload"]["owner_id"] == "test-owner"
    assert message_body["payload"]["api_key"] == "test-api-key"


def test_handle_watch_notification_token_mismatch(dynamodb_table, sqs_client):
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
    )
    repository.create(table=dynamodb_table, watch_channel=channel)

    # Call the service function with WRONG token
    with pytest.raises(BadRequestException) as exc_info:
        service.handle_watch_notification(
            table=dynamodb_table,
            queue=sqs_client,
            channel_id="test-channel-123",
            resource_state="update",
            resource_id="google-resource-456",
            channel_token="wrong-token",  # Does NOT match channel.channel_token
        )

    assert "Channel token did not match expected value" in str(exc_info.value)
    messages = sqs_client.receive_message(
        QueueUrl=settings.webhook_queue_url, MaxNumberOfMessages=1
    )
    assert "Messages" not in messages  # Queue should be empty
