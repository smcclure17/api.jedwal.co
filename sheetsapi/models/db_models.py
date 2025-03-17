"""
Database models that represent the persistence layer.
These models include DynamoDB-specific fields like PK, SK, GSI1PK, etc.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


class SheetMetadata(BaseModel):
    """Database model for sheet metadata"""

    PK: str  # SHEET#{uuid} - Primary key is now a UUID
    SK: str = "#METADATA"
    GSI1PK: str  # USER# or ORG# - For user/org ownership queries
    GSI1SK: str  # SHEET#{uuid}
    GSI2PK: str = "API"  # Consistent partition key for API name lookups
    GSI2SK: str  # API#{api_name} - For looking up sheets by API name
    sheetId: str  # Google's sheet ID
    uuid: str  # Unique identifier for the sheet (stored separately for convenience)
    apiName: str  # User-friendly API name (prefixed with owner type and ID)
    spreadsheetName: str
    createdAt: datetime | str
    cdnTtl: int
    frozen: bool = False
    authCreds: dict[str, Any]
    ownerId: str
    email: EmailStr

    @property
    def is_org_sheet(self) -> bool:
        """Returns true if sheet is owned by an org, false if personal"""
        return self.GSI1PK.startswith("ORG#")

    @property
    def org_id(self):
        if not self.is_org_sheet:
            raise ValueError("Personal sheet has no org_id")
        return self.GSI1PK[4:]

    @classmethod
    def create(
        cls,
        sheet_uuid: str,
        api_name: str,
        sheet_id: str,
        spreadsheet_name: str,
        owner_id: str,
        email: str,
        auth_creds: dict,
        is_org: bool = False,
    ):
        """Factory method to create a SheetMetadata with proper keys"""
        owner_type = "ORG" if is_org else "USER"
        return cls(
            PK=f"SHEET#{sheet_uuid}",
            GSI1PK=f"{owner_type}#{owner_id}",
            GSI1SK=f"SHEET#{sheet_uuid}",
            GSI2PK="API",
            GSI2SK=f"API#{api_name}",
            sheetId=sheet_id,
            uuid=sheet_uuid,
            apiName=api_name,
            spreadsheetName=spreadsheet_name,
            createdAt=datetime.now().isoformat(),
            cdnTtl=60,
            authCreds=auth_creds,
            ownerId=owner_id,
            email=email,
        )

    def __post_model_init__(self):
        assert self.PK.startswith("SHEET#")
        assert self.GSI1PK.startswith("USER#") or self.GSI1PK.startswith("ORG#")
        assert self.GSI1SK.startswith("SHEET#")
        assert self.GSI2PK == "API"
        assert self.GSI2SK.startswith("API#")
        assert self.SK == "#METADATA"


class SheetMetadataWithWorksheets(SheetMetadata):
    """Database model for sheet metadata with worksheets"""

    worksheets: List[str]


class UserModel(BaseModel):
    """Database model for user data"""

    PK: str
    SK: str = "#PROFILE"
    userId: str
    email: EmailStr
    refreshToken: str
    apiCount: int = 0
    premium: bool = False
    name: Optional[str] = None
    givenName: Optional[str] = None
    familyName: Optional[str] = None
    picture: Optional[str] = None
    emailVerified: Optional[bool] = None
    unsubscribed: Optional[bool] = False

    def __post_model_init__(self):
        assert self.PK.startswith("USER#")
        assert self.SK == "#PROFILE"


class PartialUserModel(BaseModel):
    """Partial database model for a user (all fields optional)"""

    PK: Optional[str] = None
    SK: Optional[str] = None
    userId: Optional[str] = None
    email: Optional[EmailStr] = None
    refreshToken: Optional[str] = None
    apiCount: Optional[int] = None
    premium: Optional[bool] = None
    name: Optional[str] = None
    givenName: Optional[str] = None
    familyName: Optional[str] = None
    picture: Optional[str] = None
    emailVerified: Optional[bool] = None


class UserLookup(BaseModel):
    """Database model for user lookup by email"""

    PK: str
    SK: str = "#LOOKUP"
    userId: str

    def __post_model_init__(self):
        assert self.PK.startswith("EMAIL#")
        assert self.SK == "#LOOKUP"


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
