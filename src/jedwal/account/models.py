import json
from typing import Annotated, Any, Literal

from pydantic import EmailStr, Field

from jedwal.common.schemas import BaseSchema, TimestampMixin

AccountStatus = Literal["free", "premium"]
AccountType = Literal["user", "organization"]

AccountId = Annotated[
    str,
    Field(
        pattern=r"^[a-zA-Z0-9-]+$",
        description="The name/ID of the account (alphanumeric and hyphens only)",
        min_length=3,
        max_length=50,
    ),
]


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

    account_id: AccountId
    email: EmailStr = Field(..., description="User email address")
    display_name: str = Field(..., description="User display name")
    given_name: str | None = Field(None, description="User's first name")
    family_name: str | None = Field(None, description="User's last name")
    account_status: AccountStatus = Field(..., description="Account status")
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token information"
    )
    do_not_email: bool | None = Field(
        default=False, description="Whether or not user has opted out of emails"
    )

    @classmethod
    def create_display_name(
        cls, given_name: str | None, family_name: str | None
    ) -> str:
        """Create display name from given and family names."""
        display_name = f"{given_name or ''} {family_name or ''}".strip()
        return display_name or "Unknown User"


class AccountRead(BaseSchema):
    id: AccountId
    account_status: str
    display_name: str
    email: EmailStr | None = Field(..., description="Email exists for users, not orgs.")

    @classmethod
    def from_account(cls, account: Account):
        return AccountRead(
            id=account.account_id,
            account_status=account.account_status,
            display_name=account.display_name,
            email=account.email,
        )

    # TODO: account could also be org, but i ignore that for now
    # due to circular import issue
    @classmethod
    def from_account_or_org(cls, account: Account):
        try:
            email = account.email
        except AttributeError:
            email = None  # account is an org with no email

        return AccountRead(
            id=account.account_id,
            account_status=account.account_status,
            display_name=account.display_name,
            email=email,
        )
