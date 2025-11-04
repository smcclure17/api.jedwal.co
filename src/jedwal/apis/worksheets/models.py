from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator

from jedwal.common.schemas import BaseSchema, TimestampMixin


class WorksheetBase(BaseSchema):
    """Base fields for worksheet operations."""

    title: str = Field(..., description="Worksheet name")


class WorksheetCreate(WorksheetBase):
    """Schema for creating a worksheet cache entry."""

    owner_id: str = Field(..., description="Owner of the parent API")
    api_key: str = Field(..., description="Parent API key")
    data: list[dict[str, Any]] = Field(..., description="Cached worksheet data")
    expires_at: datetime = Field(..., description="When cache expires (UTC)")


class Worksheet(WorksheetBase, TimestampMixin):
    """Cached worksheet data - follows parent API's cache policy.

    Cache duration is inherited from the parent API's cache_duration setting.
    When cache_duration changes on the API, all worksheet caches are invalidated.
    """

    owner_id: str = Field(..., description="Owner of the parent API")
    api_key: str = Field(..., description="Parent API key")
    data: list[dict[str, Any]] = Field(..., description="Cached worksheet data")
    expires_at: datetime = Field(..., description="When cache expires (UTC)")

    @property
    def is_expired(self) -> bool:
        """Check if cache has expired based on expires_at timestamp."""
        return datetime.now(timezone.utc) > self.expires_at


class WorksheetRead(WorksheetBase, TimestampMixin):
    """Schema for returning worksheet data to clients."""

    data: list[dict[str, Any]] = Field(..., description="Cached worksheet data")
    expires_at: datetime = Field(..., description="When cache expires (UTC)")
    is_expired: bool = Field(..., description="Whether cache has expired")


class WorksheetNamesRead(BaseSchema):
    """Response containing worksheet names for an API."""

    worksheets: list[str] = Field(..., description="List of worksheet names from Google Sheets")