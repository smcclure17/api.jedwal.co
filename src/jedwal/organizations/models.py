from typing import Literal

from pydantic import EmailStr, Field

from jedwal.common.schemas import BaseSchema, TimestampMixin

AccountStatus = Literal["free", "premium"]


class Organization(BaseSchema, TimestampMixin):
    """Organization domain model"""

    account_id: str = Field(..., description="Unique org/account identifier")
    display_name: str = Field(..., description="User display name")
    account_status: AccountStatus = Field(..., description="Account status")
    billing_account_id: str = Field(
        ..., description="ID of the account used for billing"
    )


class OrganizationCreateRequest(BaseSchema):
    organization_name: str = Field(
        ..., description="The name of the organization to create"
    )
    memberships: list[EmailStr] = Field(..., description="Account emails to invite")


class OrganizationRead(BaseSchema):
    id: str
    account_status: str
    display_name: str
    type: Literal["user", "organization"]

    @classmethod
    def from_organization(cls, account: Organization):
        return OrganizationRead(
            id=account.account_id,
            account_status=account.account_status,
            display_name=account.display_name,
            type="organization",
        )
