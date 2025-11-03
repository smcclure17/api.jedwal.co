from typing import Any

from pydantic import Field

from jedwal.account.models import RefreshTokenInfo
from jedwal.common.schemas import BaseSchema, TimestampMixin


class ApiBase(BaseSchema):
    """Base fields shared across all API operations."""

    google_sheet_id: str = Field(..., description="Google Sheet ID this API serves")
    frozen: bool = Field(default=False, description="Whether API is frozen/disabled")
    cache_duration: int = Field(
        ..., description="Cache duration in seconds for API responses", gt=0
    )


class ApiCreateRequest(ApiBase):
    """Schema for API creation request from client.

    Note: owner_id comes from the path parameter, not the request body.
    """

    pass


class ApiCreate(ApiBase):
    """Schema for creating a new API (internal)."""

    owner_id: str = Field(..., description="Account ID of the owner")
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token for accessing the sheet"
    )


class Api(ApiBase, TimestampMixin):
    """Full API domain model - internal use."""

    api_key: str = Field(..., description="Unique API key identifier")
    owner_id: str = Field(..., description="Account ID of the owner")
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token for accessing the sheet"
    )


class ApiRead(ApiBase, TimestampMixin):
    """Schema for returning API data to clients."""

    api_key: str = Field(..., description="Unique API key identifier")
    owner_id: str = Field(..., description="Account ID of the owner")
    worksheet_names: list[str] = Field(..., description="Worksheet names for the API")


class ApiUpdate(BaseSchema):
    """Schema for updating an API - all fields optional for partial updates."""

    google_sheet_id: str | None = None
    frozen: bool | None = None
    cache_duration: int | None = None


class ApiSpreadsheetDataRead(BaseSchema):
    title: str
    sheet_id: str
    data: list[dict[Any, Any]]
