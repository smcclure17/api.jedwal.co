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
    at_hash: str | None = None
    nonce: str | None = None
    name: str
    picture: str | None = None
    given_name: str
    family_name: str | None = None
    iat: int | None = None
    exp: int | None = None
    access_token: str
    # google picker api generated tokens
    picker_token: str | None = None
    picker_expires_at: int | None = None
