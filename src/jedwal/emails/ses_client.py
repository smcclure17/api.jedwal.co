import email.mime.multipart
import email.mime.text
import logging
import urllib.parse

import boto3

from jedwal.config.config import settings
from jedwal.emails.models import EmailData

logger = logging.getLogger(__name__)


def get_ses_client():
    return boto3.client("ses", region_name=settings.aws_region)


def build_unsubscribe_url(*, user_id: str, api_base_url: str) -> str:
    unsubscribe_params = {"account_id": user_id}
    unsubscribe_url = f"{api_base_url}/email/unsubscribe"
    unsubscribe_url += f"?{urllib.parse.urlencode(unsubscribe_params)}"
    return unsubscribe_url


def build_mime_message(
    *, email_data: EmailData, unsubscribe_url: str | None = None
) -> str:
    mime_msg = email.mime.multipart.MIMEMultipart()
    mime_msg["Subject"] = email_data.subject
    mime_msg["From"] = email_data.from_email
    mime_msg["To"] = email_data.to_email

    if email_data.reply_to:
        mime_msg["Reply-To"] = email_data.reply_to

    headers = email_data.headers or {}

    if unsubscribe_url and "List-Unsubscribe" not in headers:
        headers["List-Unsubscribe"] = f"<{unsubscribe_url}>"

    for name, value in headers.items():
        mime_msg[name] = value

    html_part = email.mime.text.MIMEText(email_data.html, "html", "utf-8")
    mime_msg.attach(html_part)

    return mime_msg.as_string()


def send(*, email_data: EmailData, api_base_url: str) -> dict | None:
    if not settings.emails_enabled:
        logger.warning(f"Email send disabled, skipping sending email: {email_data}")
        return None

    unsubscribe_url = None
    if email_data.user_id:
        unsubscribe_url = build_unsubscribe_url(
            user_id=email_data.user_id, api_base_url=api_base_url
        )

    mime_message = build_mime_message(
        email_data=email_data, unsubscribe_url=unsubscribe_url
    )

    client = get_ses_client()

    return client.send_raw_email(
        Source=email_data.from_email,
        ConfigurationSetName=email_data.configuration_set,
        RawMessage={"Data": mime_message},
    )
