"""
API models for external-facing interfaces.
These models define the request/response structures for API endpoints.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Any, List
from datetime import datetime

from sheetsapi.models.db_models import SheetMetadataWithWorksheets
from sheetsapi.models.domain_models import SpreadsheetDataModel
from sheetsapi.sheet_api_repo_v2 import AccountStatus


class UserDataResponse(BaseModel):
    """Public-facing API response model for user data"""

    id: str
    account_status: AccountStatus
    display_name: str
    email: EmailStr
    orgs: list[Any]


class SheetMetadataResponse(BaseModel):
    """Public-facing API response model for sheet metadata"""

    sheet_api_name: str
    owner_id: str
    created_at: datetime | str
    spreadsheet_title: str
    google_sheet_id: str  # google sheet id
    cache_duration: int
    frozen: bool = False
    worksheets: List[str] = []

    @classmethod
    def from_sheet_metadata(cls, sheet: SheetMetadataWithWorksheets):
        """Create a response model from SheetMetadataWithWorksheets"""
        return cls(
            id=sheet.PK,
            uuid=sheet.uuid,
            created_at=sheet.createdAt,
            api_name=sheet.apiName,
            api_name_formatted=sheet.apiName.replace("_", "/"),
            spreadsheet_name=sheet.spreadsheetName,
            sheet_id=sheet.sheetId,
            cdn_ttl=sheet.cdnTtl,
            frozen=sheet.frozen,
            worksheets=sheet.worksheets,
        )

    @classmethod
    def from_temp_dicts(
        cls, metadata: dict, spreadsheet_data: SpreadsheetDataModel
    ) -> "SheetMetadataResponse":
        return SheetMetadataResponse(
            sheet_api_name=metadata["sheet_api_name"],
            owner_id=metadata["owner_id"],
            created_at="placeholder",
            spreadsheet_title=spreadsheet_data.title,
            google_sheet_id=metadata["google_sheet_id"],
            cache_duration=metadata["cache_duration"],
            frozen=metadata.get("frozen"),
            worksheets=spreadsheet_data.worksheets,
        )


class UpdateApiTtlRequest(BaseModel):
    """Request model for updating API TTL"""

    owner_id: str
    sheet_api_name: str
    cache_duration: int = Field(
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


class OrganizationInviteMembersRequest(BaseModel):
    emails: list[EmailStr]


class ApiInvocationResponse(BaseModel):
    sheet_api_id: str
    path: str
    timestamp: str
    status_code: int

    @classmethod
    def from_db_dict(cls, item: dict) -> "ApiInvocationResponse":
        return ApiInvocationResponse(
            sheet_api_id=item["PK"],
            path=item["path"],
            timestamp=item["timestamp"],
            status_code=item["status_code"],
        )
