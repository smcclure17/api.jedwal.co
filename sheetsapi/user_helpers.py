import pathlib
from typing import Any, Optional
import logging

import sentry_sdk

from sheetsapi import envelope_encryption
from sheetsapi import email_client
from sheetsapi.account_repo import AccountRepo
from sheetsapi.email_client import EmailData
from sheetsapi.models.domain_models import RefreshTokenInfo, UserSession
from sheetsapi import config

WELCOME_EMAIL_PATH = (
    pathlib.Path(__file__).parent.parent / "public" / "welcome-email.html"
)

logger = logging.getLogger(__name__)


def persist_user(
    user: UserSession, refresh_token: str, account_repo: Optional[AccountRepo] = None
):
    """Store a user in the database if one does not already exist"""
    if account_repo is None:
        account_repo = AccountRepo.from_table_name()

    encryption_response = envelope_encryption.EnvelopeEncryption.encrypt(
        refresh_token, context={"account_id": user.sub}
    )

    token_info = RefreshTokenInfo(
        encrypted_refresh_token=encryption_response.encrypted_data,
        data_encryption_key=encryption_response.encrypted_key,
        context=encryption_response.context,
    )

    item = account_repo.create_user(
        user_id=user.sub,
        email=user.email,
        given_name=user.given_name,
        family_name=user.family_name,
        refresh_token_info=token_info,
    )

    try:
        # Send a welcome email to the user, and an alert to ourselves internally
        welcome_email_data = _build_welcome_email(user.email, user.given_name, user.sub)
        email_client.SESClient.send_email(welcome_email_data)
        email_client.SESClient.send_email(_build_owner_alert_email(user))
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


def _build_owner_alert_email(user: UserSession):
    return EmailData(
        subject=f"Alert: New sign-up from {user.email}",
        configuration_set="prod-sheetsapi-emails",
        reply_to="hello@jedwal.co",
        to_email="hello@jedwal.co",
        from_email="hello@jedwal.co",
        user_id=user.sub,
        html=f"<h1>New sign-up! 🎉</h1><br/><span>User {user.given_name} ({user.email}) signed up.</span>",
    )
