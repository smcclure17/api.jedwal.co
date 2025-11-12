from pydantic import EmailStr, Field

from jedwal.common.schemas import BaseSchema


class EmailData(BaseSchema):
    subject: str = Field(..., description="Email subject line")
    from_email: EmailStr = Field(..., description="Sender email address")
    to_email: EmailStr = Field(..., description="Recipient email address")
    html: str = Field(..., description="HTML content of the email")
    configuration_set: str = Field(..., description="SES configuration set name")
    user_id: str | None = Field(None, description="User ID for unsubscribe checking")
    reply_to: EmailStr | None = Field(None, description="Reply-to email address")
    headers: dict[str, str] | None = Field(None, description="Additional email headers")
