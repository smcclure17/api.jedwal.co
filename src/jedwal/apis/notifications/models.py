import hashlib
import secrets
import time

from pydantic import Field

from jedwal.account.models import AccountId
from jedwal.apis.models import ApiKey
from jedwal.common.schemas import BaseSchema, TimestampMixin


class ApiWatchChannelBase(BaseSchema):
    """Base fields for worksheet operations.

    Unique for each api_key, owner_id, and webhook_url.
    """

    api_key: ApiKey = Field(..., description="The Jedwal API this watch channel is for")
    owner_id: AccountId = Field(..., description="Owner of the parent API")
    webhook_url: str = Field(
        ...,
        description="The URL to notify the user at. Note: not supplied to Google. This is used internally",
    )
    name: str = Field(..., description="Human-readable name for this watch channel")

    @staticmethod
    def create_channel_id(owner_id: AccountId, api_key: ApiKey, webhook_url: str):
        webhook_hash = hashlib.sha256(webhook_url.encode()).hexdigest()[:10]
        return f"api_watch_channel_{owner_id}_{api_key}_{webhook_hash}"

    @staticmethod
    def create_channel_expiration(hours=24):
        """Generate a new expiration timestamp (in ms) for a watch channel"""
        return int(time.time() * 1000) + (hours * 3600 * 1000)

    @staticmethod
    def create_channel_token():
        """Generates a (secret) token used to verify incoming messages are not spoofed."""
        return secrets.token_urlsafe(32)


class ApiWatchChannel(ApiWatchChannelBase, TimestampMixin):
    """Main model of a watch channel"""

    channel_id: str = Field(..., description="The unique id of the watch channel")
    expires_at: int = Field(
        ..., description="The timestamp of when this watch channel expires"
    )
    resource_id: str = Field(
        ..., description="Google's resource ID for the watched file (from API response)"
    )
    channel_token: str = Field(
        ..., description="The secret token used to verify requests for this channel"
    )


class ApiWatchChannelRead(ApiWatchChannelBase, TimestampMixin):
    """Response model of a watch channel"""

    channel_id: str = Field(..., description="The unique id of the watch channel")


class ApiWatchChannelCreate(ApiWatchChannelBase):
    """Main model for registration/creation of a watch channel"""
