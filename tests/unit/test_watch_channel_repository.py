"""Unit tests for watch channel repository layer."""

import time
from datetime import UTC, datetime

import pytest

from jedwal.apis.notifications import repository
from jedwal.apis.notifications.models import ApiWatchChannel
from jedwal.common.exceptions import ConflictException, NotFoundException


def test_create_and_read_watch_channel(dynamodb_table):
    """Test creating and reading a watch channel."""
    channel = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="test-owner:watch:test-api-key:abc123",
        channel_token="super-secret-token",
        resource_id="google-resource-123",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook",
        expires_at=int(time.time()) + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    repository.create(table=dynamodb_table, watch_channel=channel)

    retrieved = repository.read_by_channel_id(
        table=dynamodb_table,
        channel_id=channel.channel_id,
    )

    assert retrieved is not None
    assert retrieved.channel_id == channel.channel_id
    assert retrieved.webhook_url == "https://example.com/webhook"
    assert retrieved.resource_id == "google-resource-123"


def test_create_duplicate_raises_conflict(dynamodb_table):
    """Test that creating a duplicate watch channel raises ConflictException."""
    channel = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="test:watch:api:123",
        channel_token="super-secret-token",
        resource_id="resource-123",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook",
        expires_at=int(time.time()) + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    repository.create(table=dynamodb_table, watch_channel=channel)

    with pytest.raises(ConflictException):
        repository.create(table=dynamodb_table, watch_channel=channel)


def test_read_nonexistent_returns_none(dynamodb_table):
    """Test reading a nonexistent watch channel returns None."""
    result = repository.read_by_channel_id(
        table=dynamodb_table, channel_id="nonexistent"
    )

    assert result is None


def test_read_by_channel_id(dynamodb_table):
    """Test reading a watch channel by channel_id (for webhook lookup)."""
    channel = ApiWatchChannel(
        owner_id="owner-123",
        api_key="api-key-456",
        channel_id="unique-channel-id",
        channel_token="super-secret-token",
        resource_id="resource-789",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook",
        expires_at=int(time.time()) + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    repository.create(table=dynamodb_table, watch_channel=channel)

    retrieved = repository.read_by_channel_id(
        table=dynamodb_table, channel_id="unique-channel-id"
    )

    assert retrieved is not None
    assert retrieved.channel_id == "unique-channel-id"
    assert retrieved.owner_id == "owner-123"
    assert retrieved.api_key == "api-key-456"


def test_list_channels_for_api(dynamodb_table):
    """Test listing all watch channels for a specific API."""
    # Create two channels for same API
    channel1 = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="channel-1",
        channel_token="super-secret-token",
        resource_id="resource-1",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook1",
        expires_at=int(time.time()) + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    channel2 = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="channel-2",
        resource_id="resource-2",
        channel_token="super-secret-token",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook2",
        expires_at=int(time.time()) + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Create channel for different API
    different_api = ApiWatchChannel(
        owner_id="test-owner",
        api_key="different-api-key",
        channel_id="channel-3",
        channel_token="super-secret-token",
        resource_id="resource-3",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook3",
        expires_at=int(time.time()) + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    repository.create(table=dynamodb_table, watch_channel=channel1)
    repository.create(table=dynamodb_table, watch_channel=channel2)
    repository.create(table=dynamodb_table, watch_channel=different_api)

    channels = repository.list_channels_for_api(
        table=dynamodb_table, owner_id="test-owner", api_key="test-api-key"
    )

    assert len(channels) == 2
    channel_ids = {ch.channel_id for ch in channels}
    assert "channel-1" in channel_ids
    assert "channel-2" in channel_ids
    assert "channel-3" not in channel_ids


def test_list_channels_empty(dynamodb_table):
    """Test listing channels for an API with no channels returns empty list."""
    channels = repository.list_channels_for_api(
        table=dynamodb_table, owner_id="nonexistent", api_key="nonexistent"
    )

    assert channels == []


def test_delete_watch_channel(dynamodb_table):
    """Test deleting a watch channel."""
    channel = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="test-channel",
        channel_token="super-secret-token",
        resource_id="resource-123",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook",
        expires_at=int(time.time()) + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    repository.create(table=dynamodb_table, watch_channel=channel)

    repository.delete(
        table=dynamodb_table,
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="test-channel",
    )

    retrieved = repository.read_by_channel_id(
        table=dynamodb_table, channel_id="test-channel"
    )

    assert retrieved is None


def test_delete_nonexistent_raises_not_found(dynamodb_table):
    """Test deleting a nonexistent watch channel raises NotFoundException."""
    with pytest.raises(NotFoundException):
        repository.delete(
            table=dynamodb_table,
            owner_id="nonexistent",
            api_key="nonexistent",
            channel_id="nonexistent",
        )


def test_get_soon_to_expire_channels(dynamodb_table):
    """Test getting channels that will expire soon."""
    now = int(time.time())

    # Channel expiring in 1 hour
    expiring_soon = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="expiring-soon",
        channel_token="super-secret-token",
        resource_id="resource-1",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook1",
        expires_at=now + 3600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Channel expiring in 24 hours
    expiring_later = ApiWatchChannel(
        owner_id="test-owner",
        api_key="test-api-key",
        channel_id="expiring-later",
        channel_token="super-secret-token",
        resource_id="resource-2",
        name="some-watch-channel-name",
        webhook_url="https://example.com/webhook2",
        expires_at=now + 86400,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    repository.create(table=dynamodb_table, watch_channel=expiring_soon)
    repository.create(table=dynamodb_table, watch_channel=expiring_later)

    # Query for channels expiring in next 12 hours
    expires_before = now + (12 * 3600)
    channels = repository.get_soon_to_expire_channels(
        table=dynamodb_table, expires_before=expires_before
    )

    assert len(channels) == 1
    assert channels[0].channel_id == "expiring-soon"
