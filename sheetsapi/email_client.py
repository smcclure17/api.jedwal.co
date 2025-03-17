from typing import Dict, List, Optional
import logging
import dataclasses
import urllib.parse
import email.mime.multipart
import email.mime.text
import email.utils

import boto3
from sheetsapi.config import Config

Config.init()


_logger = logging.getLogger(__name__)


@dataclasses.dataclass
class EmailData:
    subject: str
    from_email: str
    reply_to: Optional[str]
    to_email: str
    html: str
    configuration_set: str
    user_id: str
    headers: Optional[Dict[str, str]] = None


class SESClient:
    @staticmethod
    def get_ses_client():
        return boto3.client("ses", region_name=Config.Constants.AWS_REGION)

    @staticmethod
    def check_if_unsubscribed(user_id: str) -> bool:
        """Check if a user has unsubscribed from emails.

        Returns:
            True if the user has unsubscribed, False otherwise
        """
        from sheetsapi.sheet_api_repo_v2 import SheetApiRepo

        repo = SheetApiRepo.from_table_name()

        user = repo.get_account(user_id)
        if user and user.get("unsubscribed", False):
            return True

        return False

    @staticmethod
    def send_email(email_data: EmailData) -> Optional[dict]:
        if not Config.Constants.EMAILS_ENABLED:
            _logger.warning(
                f"Email send disabled, skipping sending email: {email_data}."
            )
            return None

        if email_data.user_id and SESClient.check_if_unsubscribed(email_data.user_id):
            _logger.info(
                f"User {email_data.to_email} has unsubscribed, skipping email."
            )
            return None

        # Add List-Unsubscribe header if not present
        if not email_data.headers:
            email_data.headers = {}

        # Generate unsubscribe URL with user ID
        unsubscribe_params = {"user_id": email_data.user_id}
        unsubscribe_url = f"{Config.Constants.API_BASE_URL}/unsubscribe"
        unsubscribe_url += f"?{urllib.parse.urlencode(unsubscribe_params)}"

        if "List-Unsubscribe" not in email_data.headers:
            email_data.headers["List-Unsubscribe"] = f"<{unsubscribe_url}>"

        client = SESClient.get_ses_client()

        # Create a multipart MIME message
        mime_msg = email.mime.multipart.MIMEMultipart()
        mime_msg["Subject"] = email_data.subject
        mime_msg["From"] = email_data.from_email
        mime_msg["To"] = email_data.to_email
        if email_data.reply_to:
            mime_msg["Reply-To"] = email_data.reply_to

        # Add List-Unsubscribe and any other headers
        if email_data.headers:
            for name, value in email_data.headers.items():
                mime_msg[name] = value

        # Attach HTML part
        html_part = email.mime.text.MIMEText(email_data.html, "html", "utf-8")
        mime_msg.attach(html_part)

        # Send raw email
        return client.send_raw_email(
            Source=email_data.from_email,
            ConfigurationSetName=email_data.configuration_set,
            RawMessage={"Data": mime_msg.as_string()},
        )
