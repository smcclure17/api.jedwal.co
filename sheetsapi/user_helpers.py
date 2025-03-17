import pathlib
from typing import Any, Optional
import logging

import sentry_sdk

from sheetsapi import envelope_encryption
from sheetsapi import email_client
from sheetsapi.email_client import EmailData
from sheetsapi.sheet_api_repo_v2 import SheetApiRepo
from sheetsapi.models.domain_models import RefreshTokenInfo, UserSession
from sheetsapi import config

WELCOME_EMAIL_PATH = (
    pathlib.Path(__file__).parent.parent / "public" / "welcome-email.html"
)

logger = logging.getLogger(__name__)


def persist_user(
    user: UserSession, refresh_token: str, sheet_repo: Optional[SheetApiRepo] = None
):
    """Store a user in the database if one does not already exist"""
    if sheet_repo is None:
        sheet_repo = SheetApiRepo.from_table_name()

    encryption_response = envelope_encryption.EnvelopeEncryption.encrypt(
        refresh_token, context={"account_id": user.sub}
    )

    token_info = RefreshTokenInfo(
        encrypted_refresh_token=encryption_response.encrypted_data,
        data_encryption_key=encryption_response.encrypted_key,
        context=encryption_response.context,
    )

    item = sheet_repo.create_user(
        user_id=user.sub,
        email=user.email,
        given_name=user.given_name,
        family_name=user.family_name,
        refresh_token_info=token_info,
    )

    try:
        email_client.SESClient.send_email(
            _build_welcome_email(user.email, user.given_name, user.sub)
        )
    except Exception as err:
        sentry_sdk.capture_exception(err)
        logger.warning(
            f"Failed to send welcome email to {user.email}. Error {str(err)}"
        )
    return item["account_id"]


def _build_welcome_email(to_email: str, account_first_name: str, user_id) -> EmailData:
    welcome_email_html = WELCOME_EMAIL_PATH.read_text()
    welcome_email_html = welcome_email_html.replace(
        "{{first_name}}", account_first_name
    )

    # Generate unsubscribe link
    unsubscribe_link = (
        f"{config.Config.Constants.API_BASE_URL}/unsubscribe?user_id={user_id}"
    )
    welcome_email_html = welcome_email_html.replace(
        "{{unsubscribe_link}}", unsubscribe_link
    )

    return EmailData(
        subject="Welcome to Jedwal!",
        from_email="Sean at Jedwal <hello@jedwal.co>",
        reply_to="hello@jedwal.co",
        to_email=to_email,
        html=welcome_email_html,
        configuration_set="prod-sheetsapi-emails",  # hard-coded from CloudFormation template
        user_id=user_id,
    )
