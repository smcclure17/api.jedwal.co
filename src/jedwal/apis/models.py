from datetime import datetime
from typing import Annotated, Any

from pydantic import Field

from jedwal.account.models import AccountId, RefreshTokenInfo
from jedwal.common.schemas import BaseSchema, TimestampMixin

ApiKey = Annotated[
    str,
    Field(
        pattern=r"^[a-zA-Z0-9-]+$",
        description="The name/ID of the API (alphanumeric and hyphens only)",
        min_length=3,
        max_length=50,
    ),
]


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

    owner_id: AccountId = Field(..., description="Account ID of the owner")
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token for accessing the sheet"
    )


class Api(ApiBase, TimestampMixin):
    """Full API domain model - internal use."""

    api_key: ApiKey = Field(..., description="Unique API key identifier")
    owner_id: AccountId = Field(..., description="Account ID of the owner")
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token for accessing the sheet"
    )
    spreadsheet_title: str | None = Field(
        None, description="Cached title of the Google Spreadsheet"
    )


class ApiRead(ApiBase, TimestampMixin):
    """Schema for returning API data to clients."""

    api_key: ApiKey = Field(..., description="Unique API key identifier")
    owner_id: AccountId = Field(..., description="Account ID of the owner")
    spreadsheet_title: str | None = Field(
        None, description="Cached title of the Google Spreadsheet"
    )


class ApiCreateRead(BaseSchema):
    api_key: ApiKey = Field(..., description="ID of the newly created API.")


class ApiUpdate(BaseSchema):
    """Schema for updating an API - all fields optional for partial updates."""

    cache_duration: int | None = None


class ApiSpreadsheetDataRead(BaseSchema):
    title: str
    sheet_id: str
    data: list[dict[Any, Any]]
    expires_at: datetime
