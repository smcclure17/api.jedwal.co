import json
from typing import Any, Literal

from pydantic import EmailStr, Field

from jedwal.common.schemas import BaseSchema, TimestampMixin

AccountStatus = Literal["free", "premium"]


class RefreshTokenInfo(BaseSchema):
    """The encrypted refresh token, and the fields needed to decrypt it."""

    encrypted_refresh_token: str
    data_encryption_key: str
    context: dict[str, Any]

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict_str(cls, item: str) -> "RefreshTokenInfo":
        return RefreshTokenInfo(**json.loads(item))  # for testing only


class Account(BaseSchema, TimestampMixin):
    """Account domain model"""

    account_id: str = Field(..., description="Unique account identifier")
    email: EmailStr = Field(..., description="User email address")
    display_name: str = Field(..., description="User display name")
    given_name: str | None = Field(None, description="User's first name")
    family_name: str | None = Field(None, description="User's last name")
    account_status: AccountStatus = Field(..., description="Account status")
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token information"
    )

    @classmethod
    def create_display_name(
        cls, given_name: str | None, family_name: str | None
    ) -> str:
        """Create display name from given and family names."""
        display_name = f"{given_name or ''} {family_name or ''}".strip()
        return display_name or "Unknown User"


class AccountRead(BaseSchema):
    id: str
    account_status: str
    display_name: str
    email: EmailStr
    type: Literal["user", "org"]

    @classmethod
    def from_account(cls, account: Account):
        return AccountRead(
            id=account.account_id,
            account_status=account.account_status,
            display_name=account.display_name,
            email=account.email,
            type="user",
        )
