"""
Core domain models that represent business entities independent of persistence or API concerns.
"""

import json
from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any


class UserSession(BaseModel):
    """Google Account user session data."""

    iss: str
    azp: str
    aud: str
    sub: str
    email: EmailStr
    email_verified: bool
    at_hash: str
    nonce: str
    name: str
    picture: str
    given_name: str
    family_name: str
    iat: int
    exp: int
    access_token: str


class SpreadsheetDataModel(BaseModel):
    """Data model for Google Spreadsheet"""

    title: str
    worksheets: List[str]


class WorksheetDataModel(BaseModel):
    """Data model for worksheet data from Google Sheets"""

    title: str
    data: List[Dict[str, Any]]


class EncryptionOutput(BaseModel):
    """Result of an encryption call"""

    encrypted_data: str
    encrypted_key: str
    context: Dict[str, Any]


class RefreshTokenInfo(BaseModel):
    """The encrypted refresh token, and the fields needed to decrypt it."""

    encrypted_refresh_token: str
    data_encryption_key: str
    context: dict[str, Any]

    def to_dict(self) -> dict:
        return self.model_dump()
    
    @classmethod
    def from_dict_str(cls, item: str) -> "RefreshTokenInfo":
        return RefreshTokenInfo(**json.loads(item))  # no validation b/c only used in testing
    
