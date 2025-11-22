import pathlib

from jedwal.account.models import AccountId
from jedwal.config import settings
from jedwal.emails.models import EmailData

WELCOME_EMAIL_PATH = pathlib.Path(__file__).parents[3] / "public" / "welcome-email.html"


def build_welcome_email(to_email: str, account_first_name: str, user_id) -> EmailData:
    welcome_email_html = WELCOME_EMAIL_PATH.read_text()
    welcome_email_html = welcome_email_html.replace(
        "{{first_name}}", account_first_name
    )

    # Generate unsubscribe link
    unsubscribe_link = f"{settings.api_base_url}/unsubscribe?user_id={user_id}"
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


def build_owner_alert_email(email: str, display_name: str, account_id: AccountId):
    return EmailData(
        subject=f"Alert: New sign-up from {email}",
        configuration_set="prod-sheetsapi-emails",
        reply_to="hello@jedwal.co",
        to_email="hello@jedwal.co",
        from_email="hello@jedwal.co",
        user_id=account_id,
        html=f"<h1>New sign-up! 🎉</h1><br/><span>User {display_name} ({email}) signed up.</span>",
    )
