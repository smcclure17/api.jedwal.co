
from typing import Optional
from pydantic import EmailStr
from jedwal.common.schemas import BaseSchema


class GoogleAccountSession(BaseSchema):
    """Google Account user session data."""

    iss: str
    azp: str
    aud: str
    sub: str
    email: EmailStr
    email_verified: bool = True
    at_hash: Optional[str] = None
    nonce: Optional[str] = None
    name: str
    picture: Optional[str] = None
    given_name: str
    family_name: Optional[str] = None
    iat: Optional[int] = None
    exp: Optional[int] = None
    access_token: str
    # google picker api generated tokens
    picker_token: Optional[str] = None
    picker_expires_at: Optional[int] = None