"""Common Pydantic schemas."""

from datetime import datetime, timezone
from functools import partial

from pydantic import BaseModel, ConfigDict, Field

utcnow = partial(datetime.now, timezone.utc)


class TimestampMixin(BaseModel):
    """Mixin for timestamp fields."""

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

