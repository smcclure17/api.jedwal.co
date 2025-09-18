from datetime import datetime
from typing import Optional
import stripe
from sheetsapi import account_repo
from sheetsapi.config import Config


Config.init()
stripe.api_key = Config.Constants.STRIPE_SECRET_KEY
WEBHOOK_SECRET = Config.Constants.STRIPE_WEBHOOK_SECRET


class StripeHandler:
    def __init__(self, repo: Optional[account_repo.AccountRepo] = None):
        if repo is None:
            repo = account_repo.AccountRepo.from_table_name()
        self.repo = repo

    def update_billing_period(self, email, start: datetime, end: datetime):
        start = _dt_to_date_str(start)
        end = _dt_to_date_str(end)

        user = self.repo.get_user_by_email(email)
        body = {
            "billing_start": start,
            "billing_end": end,
            "GSI4PK": f"ACCOUNT#BILLING_END#{end}",
        }
        self.repo.update_account(user["account_id"], body)

    def upgrade_user(self, email: str) -> None:
        """Mark a user as a premium user"""
        user = self.repo.get_user_by_email(email)
        if user is None:
            raise account_repo.UserNotFoundError(
                f"Cannot find user for email Stripe email {email}"
            )
        self.repo.upgrade_account(owner_id=user["account_id"])

    def downgrade_user(self, customer_id: str) -> None:
        """Mark a user as basic"""
        customer = stripe.Customer.retrieve(customer_id)
        email = customer.email
        if email is None:
            raise ValueError(
                f"Cannot cancel subscription with no email. Customer ID: {customer_id}"
            )

        user = self.repo.get_user_by_email(email=email)
        if user is None:
            raise account_repo.UserNotFoundError(
                f"Cannot find user for email {email} from Stripe ID: {customer_id}"
            )
        self.repo.downgrade_account(owner_id=user["account_id"])

    @staticmethod
    def get_event(payload, header):
        return stripe.Webhook.construct_event(payload, header, WEBHOOK_SECRET)

    def send_past_due_warning_email(self, user_id: str):
        pass  # TODO: implement


def _dt_to_date_str(dt: datetime):
    return dt.strftime("%Y-%m-%d")
