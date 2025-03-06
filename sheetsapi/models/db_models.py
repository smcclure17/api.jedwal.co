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

    PK: str
    SK: str = "#METADATA"
    GSI1PK: str
    GSI1SK: str
    sheetId: str
    apiName: str
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

    def __post_model_init__(self):
        assert self.PK.startswith("SHEET#")
        assert self.GSI1PK.startswith("USER#")
        assert self.GSI1SK.startswith("SHEET#")
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
