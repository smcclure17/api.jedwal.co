"""
Database models that represent the persistence layer.
These models include DynamoDB-specific fields like PK, SK, GSI1PK, etc.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

from sheetsapi.models.domain_models import RefreshTokenInfo


class OrganizationModel(BaseModel):
    """Database model for organization data"""

    PK: str
    SK: str = "#METADATA"
    GSI1PK: str  # ORG#<orgId>
    GSI1SK: str = "#METADATA"
    orgId: str
    name: str
    createdAt: datetime | str
    createdBy: str  # userId of creator

    def __post_model_init__(self):
        assert self.PK.startswith("ORG#")
        assert self.SK == "#METADATA"
        assert self.GSI1PK.startswith("ORG#")
        assert self.GSI1SK == "#METADATA"


class OrganizationMembership(BaseModel):
    """Database model for organization membership"""

    PK: str  # USER#<userId>
    SK: str  # ORG#<orgId>
    GSI1PK: str  # ORG#<orgId>
    GSI1SK: str  # USER#<userId>
    userId: str
    orgId: str
    email: EmailStr
    role: str = "member"  # member, admin, etc.
    joinedAt: datetime | str

    def __post_model_init__(self):
        assert self.PK.startswith("USER#")
        assert self.SK.startswith("ORG#")
        assert self.GSI1PK.startswith("ORG#")
        assert self.GSI1SK.startswith("USER#")


class RateLimitRecord(BaseModel):
    """Database model for rate limiting records"""

    PK: str  # RATE#<resource_type>#<resource_id>
    SK: str  # <timestamp_minute>
    count: int = 0
    expiresAt: int  # TTL attribute for automatic deletion

    @classmethod
    def create(
        cls,
        resource_type: str,
        resource_id: str,
        timestamp_minute: str,
        ttl_seconds: int = 120,
    ):
        """Create a rate limit record for a specific minute window

        Args:
            resource_type: Type of resource (IP, API, USER, etc.)
            resource_id: ID of the resource (IP address, API ID, user ID)
            timestamp_minute: ISO timestamp rounded to the minute (YYYY-MM-DDTHH:MM)
            ttl_seconds: Time to live in seconds (default: 120s = 2 minutes)

        Returns:
            RateLimitRecord: New rate limit record
        """
        import time

        current_time = int(time.time())
        expires_at = current_time + ttl_seconds

        return cls(
            PK=f"RATE#{resource_type}#{resource_id}",
            SK=timestamp_minute,
            count=1,
            expiresAt=expires_at,
        )


class DocApi(BaseModel):
    PK: str
    SK: str
    doc_api_name: str
    owner_id: str
    google_doc_id: str
    google_doc_payload: dict | str
    title: Optional[str] = None
    refresh_token_info: RefreshTokenInfo
    frozen: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_modified: str = Field(default_factory=lambda: datetime.now().isoformat())
    GSI2PK: str
    GSI2SK: str

    @classmethod
    def from_dict(cls, item: dict):
        item["refresh_token_info"] = RefreshTokenInfo(**item["refresh_token_info"])
        return DocApi(**item)
