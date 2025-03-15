import stripe
from sheetsapi import sheet_api_repo_v2
from sheetsapi.config import Config

Config.init()
stripe.api_key = Config.Constants.STRIPE_SECRET_KEY
WEBHOOK_SECRET = Config.Constants.STRIPE_WEBHOOK_SECRET


def upgrade_user(email: str) -> None:
    """Mark a user as a premium user"""

    repo = sheet_api_repo_v2.SheetApiRepo.from_table_name()
    user = repo.get_user_by_email(email)
    if user is None:
        raise sheet_api_repo_v2.UserNotFoundError(
            f"Cannot find user for email Stripe email {email}"
        )
    repo.upgrade_account(owner_id=user["user_id"])


def downgrade_user(customer_id: str) -> None:
    """Mark a user as basic"""
    customer = stripe.Customer.retrieve(customer_id)
    email = customer.email
    if email is None:
        raise ValueError(
            f"Cannot cancel subscription with no email. Customer ID: {customer_id}"
        )

    repo = sheet_api_repo_v2.SheetApiRepo.from_table_name()
    user = repo.get_user_by_email(email=email)
    if user is None:
        raise sheet_api_repo_v2.UserNotFoundError(
            f"Cannot find user for email {email} from Stripe ID: {customer_id}"
        )
    repo.downgrade_account(owner_id=user["user_id"])


def get_event(payload, header):
    return stripe.Webhook.construct_event(payload, header, WEBHOOK_SECRET)
