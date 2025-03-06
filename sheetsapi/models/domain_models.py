"""
Core domain models that represent business entities independent of persistence or API concerns.
"""

from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Optional


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
    refresh_token: Optional[str] = None


class SpreadsheetDataModel(BaseModel):
    """Data model for Google Spreadsheet"""

    title: str
    worksheets: List[str]


class WorksheetDataModel(BaseModel):
    """Data model for worksheet data from Google Sheets"""

    title: str
    data: List[Dict[str, Any]]
