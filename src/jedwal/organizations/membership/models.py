from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from jedwal.common.schemas import BaseSchema

MemberType = Literal["owner", "member"]


class Membership(BaseSchema):
    account_id: str = Field(..., description="The account in the org")
    organization_id: str = Field(..., description="The org the account belongs to")
    member_type: MemberType = Field(..., description="Role the account has in the org.")
    joined_at: datetime = Field(..., description="When the account joined the org")


class MembershipRead(Membership):
    """Membership item for public reads"""


class MembershipCreate(BaseSchema):
    member_type: MemberType = Field(..., description="Role the account has in the org.")
    email: EmailStr = Field(..., description="The email of the user to invite.")


class MembershipCreateRequest(BaseSchema):
    memberships: list[MembershipCreate]
