"""
API models for external-facing interfaces.
These models define the request/response structures for API endpoints.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Annotated, Any, List
from datetime import datetime

from sheetsapi.models.db_models import DocApi
from sheetsapi.models.domain_models import SpreadsheetDataModel
from sheetsapi.account_repo import AccountStatus, AccountType


class UserDataResponse(BaseModel):
    """Public-facing API response model for user data"""

    id: str
    account_status: AccountStatus
    display_name: str
    email: EmailStr
    orgs: list[Any]
    type: AccountType


class SheetMetadata(BaseModel):
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
    def from_temp_dicts(
        cls, metadata: dict, spreadsheet_data: SpreadsheetDataModel
    ) -> "SheetMetadata":
        return SheetMetadata(
            sheet_api_name=metadata["sheet_api_name"],
            owner_id=metadata["owner_id"],
            created_at="placeholder",
            spreadsheet_title=spreadsheet_data.title,
            google_sheet_id=metadata["google_sheet_id"],
            cache_duration=metadata["cache_duration"],
            frozen=metadata.get("frozen"),
            worksheets=spreadsheet_data.worksheets,
        )


class SheetMetadataFailure(BaseModel):
    sheet_api_name: str
    google_sheet_id: str
    hint: Annotated[str, "A hint as to why the sheet failed to fetch"]


class GetAllSheetsResponse(BaseModel):
    results: list[SheetMetadata]
    failures: list[SheetMetadataFailure]


class UpdateApiTtlRequest(BaseModel):
    """Request model for updating API TTL"""

    owner_id: str
    api_name: str
    cache_duration: int = Field(
        gt=0, description="Cache duration in seconds, minimum 1 second"
    )

class PublishDocApiRequest(BaseModel):
    """Update Doc API content to match Google Doc"""
    owner_id: str
    api_name: str


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
            sheet_api_id=item["sheet_api_name"],
            path=item["path"],
            timestamp=item["request_time"],
            status_code=item["status_code"],
        )


class DocApiResponse(BaseModel):
    doc_api_name: str
    owner_id: str
    google_doc_id: str
    frozen: bool = False
    cache_duration: int
    created_at: str
    title: str

    @classmethod
    def from_doc_api(cls, api: DocApi, title: str = None):
        return DocApiResponse(
            doc_api_name=api.doc_api_name,
            owner_id=api.owner_id,
            google_doc_id=api.google_doc_id,
            frozen=api.frozen,
            cache_duration=api.cache_duration,
            created_at=api.created_at,
            title=title or "Untitled Post"
        )
    
    def to_dict(self):
        return self.model_dump()
