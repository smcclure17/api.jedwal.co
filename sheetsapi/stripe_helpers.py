import stripe
from sheetsapi import dynamodb_client
from sheetsapi.config import Config

Config.init()
stripe.api_key = Config.Constants.STRIPE_SECRET_KEY
WEBHOOK_SECRET = Config.Constants.STRIPE_WEBHOOK_SECRET


def upgrade_user(email: str) -> None:
    """Mark a user as a premium user"""
    repo = dynamodb_client.DynamoDBClient()
    res = repo.update_item(
        table=Config.Constants.SHEETS_API_TABLE,
        key={"id": f"user-{email}"},
        item={"premium": True},
    )


def downgrade_user(customer_id: str) -> None:
    """Mark a user as basic"""
    customer = stripe.Customer.retrieve(customer_id)
    email = customer.email
    if email is None:
        raise ValueError(
            f"Cannot cancel subscription with no email. Customer ID: {customer_id}"
        )

    repo = dynamodb_client.DynamoDBClient()
    res = repo.update_item(
        table=Config.Constants.SHEETS_API_TABLE,
        key={"id": f"user-{email}"},
        item={"premium": False},
    )


def get_event(payload, header):
    return stripe.Webhook.construct_event(payload, header, WEBHOOK_SECRET)
