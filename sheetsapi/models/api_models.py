"""
API models for external-facing interfaces.
These models define the request/response structures for API endpoints.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Annotated, Any, Dict, List, Optional, Literal
from datetime import datetime
import ipaddress
from urllib.parse import urlparse
import json


from sheetsapi.models.db_models import DocApi, WebhookIntegration
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


class AddCategoryToDocRequest(BaseModel):
    """Request model for adding category to a Doc API"""

    owner_id: str
    api_name: str
    category: str


class UpdateDocApiSlugRequest(BaseModel):
    """Request model for changing the slug for a Doc API"""

    owner_id: str
    api_name: str
    slug: str


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
    created_at: str
    title: str
    last_modified: str
    categories: Optional[list[str]] = None
    slug: Optional[str] = None
    webhooks: Optional[list[WebhookIntegration]]

    @classmethod
    def from_doc_api(cls, api: DocApi, title: str = None):
        return DocApiResponse(
            doc_api_name=api.doc_api_name,
            owner_id=api.owner_id,
            google_doc_id=api.google_doc_id,
            frozen=api.frozen,
            created_at=api.created_at,
            title=title or "Untitled Post",
            last_modified=api.last_modified,
            categories=api.categories,
            slug=api.custom_slug or api.doc_api_name,
            webhooks=api.webhooks,
        )

    def to_dict(self):
        return self.model_dump()


class DocApiPublicResponse(BaseModel):
    doc_api_name: str
    owner_id: str
    frozen: bool = False
    created_at: str
    title: str
    last_modified: str
    categories: Optional[list[str]] = None
    slug: Optional[str] = None

    @classmethod
    def from_doc_api(cls, api: DocApi, title: str = None):
        return DocApiPublicResponse(
            doc_api_name=api.doc_api_name,
            owner_id=api.owner_id,
            frozen=api.frozen,
            created_at=api.created_at,
            title=title or "Untitled Post",
            last_modified=api.last_modified,
            categories=api.categories,
            slug=api.custom_slug or api.doc_api_name,
        )

    def to_dict(self):
        return self.model_dump()


class WebhookIntegrationRequestObject(BaseModel):
    url: str
    method: Literal["GET", "POST"]
    payload: Dict[str, Any] = {}
    name: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        """Validate webhook URL for security and correctness"""
        if not v:
            raise ValueError("URL cannot be empty")

        try:
            parsed = urlparse(v)
        except Exception:
            raise ValueError("Invalid URL format")

        # Only allow HTTP/HTTPS
        if parsed.scheme not in ["http", "https"]:
            raise ValueError("Only HTTP and HTTPS protocols are allowed")

        # Require hostname
        if not parsed.hostname:
            raise ValueError("URL must include a valid hostname")

        # Block localhost and private IP ranges
        hostname = parsed.hostname.lower()

        # Block localhost variants
        if hostname in ["localhost", "127.0.0.1", "::1"]:
            raise ValueError("Localhost URLs are not allowed")

        # Try to parse as IP address and block private ranges
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ValueError(
                    "Private, loopback, and link-local IP addresses are not allowed"
                )
        except ValueError:
            # Not an IP address, continue with hostname validation
            pass

        # Block common private/internal hostnames
        blocked_hostnames = [
            "metadata.google.internal",
            "instance-data",
            "internal",
            "0.0.0.0",
        ]

        for blocked in blocked_hostnames:
            if blocked in hostname:
                raise ValueError(f"Hostname '{hostname}' is not allowed")

        # Block suspicious URL patterns
        suspicious_patterns = ["file://", "ftp://", "data:", "javascript:", "vbscript:"]

        v_lower = v.lower()
        for pattern in suspicious_patterns:
            if pattern in v_lower:
                raise ValueError(f"URL contains blocked pattern: {pattern}")

        # Ensure reasonable URL length
        if len(v) > 2000:
            raise ValueError("URL is too long (max 2000 characters)")

        return v

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        """Validate payload based on HTTP method"""
        # Access other field values using info.data
        method = info.data.get("method", "POST") if info.data else "POST"

        # GET requests shouldn't have payloads
        if method == "GET" and v:
            raise ValueError("GET requests cannot have a payload")

        # Limit payload size (rough JSON size check)
        try:
            json_str = json.dumps(v)
            if len(json_str) > 50000:  # ~50KB limit
                raise ValueError("Payload is too large (max 50KB)")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Payload must be JSON serializable: {e}")

        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://api.example.com/webhooks",
                "method": "POST",
                "payload": {
                    "event": "site.republished",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            }
        }
    }


class AddWebhookToDocApiRequest(BaseModel):
    owner_id: str
    api_name: str
    webhook: WebhookIntegrationRequestObject


class DeleteWebhookToDocApiRequest(BaseModel):
    owner_id: str
    api_name: str
    url: str


class DocsMetadataResponse(BaseModel):
    apis: List[DocApiResponse]


class DocsPublicMetadataResponse(BaseModel):
    apis: List[DocApiPublicResponse]


class DocApiContentResponse(BaseModel):
    content: str
    title: str
    published_at: Optional[str] = None
    creator: Optional[str] = None

class CreateDocResponse(BaseModel):
    url: str
    post_id: str
