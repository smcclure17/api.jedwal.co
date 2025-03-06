"""
API models for external-facing interfaces.
These models define the request/response structures for API endpoints.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import List
from datetime import datetime

from sheetsapi.models.db_models import SheetMetadataWithWorksheets


class UserDataResponse(BaseModel):
    """Public-facing API response model for user data"""

    api_count: int = Field(gt=-1)
    id: str
    premium: bool
    name: str
    email: EmailStr


class SheetMetadataResponse(BaseModel):
    """Public-facing API response model for sheet metadata"""

    id: str
    created_at: datetime | str
    api_name: str
    spreadsheet_name: str
    sheet_id: str
    cdn_ttl: int
    frozen: bool = False
    worksheets: List[str] = []

    @classmethod
    def from_sheet_metadata(cls, sheet: SheetMetadataWithWorksheets):
        """Create a response model from SheetMetadataWithWorksheets"""
        return cls(
            id=sheet.PK,
            created_at=sheet.createdAt,
            api_name=sheet.apiName,
            spreadsheet_name=sheet.spreadsheetName,
            sheet_id=sheet.sheetId,
            cdn_ttl=sheet.cdnTtl,
            frozen=sheet.frozen,
            worksheets=sheet.worksheets,
        )


class UpdateApiTtlRequest(BaseModel):
    """Request model for updating API TTL"""

    name: str
    cdn_ttl: int = Field(
        gt=0, description="Cache duration in seconds, minimum 1 second"
    )


class UpdateApiTtlResponse(BaseModel):
    """Response model for updating API TTL"""

    message: str


class CreateOrganizationRequest(BaseModel):
    """Request model for creating an organization"""

    name: str = Field(..., min_length=1, max_length=100)
    invitees: list[EmailStr]


class OrganizationResponse(BaseModel):
    """Response model for organization data"""

    id: str
    name: str
    created_at: datetime | str
    created_by: str


class OrganizationMemberResponse(BaseModel):
    """Response model for organization member data"""

    user_id: str
    email: EmailStr
    role: str
    joined_at: datetime | str


class OrganizationMembersResponse(BaseModel):
    """Response model for listing organization members"""

    organization: OrganizationResponse
    members: List[OrganizationMemberResponse]
