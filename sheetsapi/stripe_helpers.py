import stripe
from sheetsapi import dynamodb_client, google_sheets
from sheetsapi.config import Config

Config.init()
stripe.api_key = Config.Constants.STRIPE_SECRET_KEY
WEBHOOK_SECRET = Config.Constants.STRIPE_WEBHOOK_SECRET


def upgrade_user(email: str, google_sheets_client: google_sheets.GoogleSheets) -> None:
    """Mark a user as a premium user"""
    repo = dynamodb_client.DynamoDBClient()

    # mark as premium user
    repo.update_item(
        table=Config.Constants.SHEETS_API_TABLE,
        key={"id": f"user-{email}"},
        item={"premium": True},
    )

    # reactivate any APIs that might be frozen
    sheets = google_sheets_client.get_sheets_for_email(email=email)
    for sheet in sheets:
        repo.update_item(
            Config.Constants.SHEETS_API_TABLE,
            key={"id": sheet["id"]},
            item={"frozen": False},
        )


def downgrade_user(
    customer_id: str, google_sheets_client: google_sheets.GoogleSheets
) -> None:
    """Mark a user as basic"""
    customer = stripe.Customer.retrieve(customer_id)
    email = customer.email
    if email is None:
        raise ValueError(
            f"Cannot cancel subscription with no email. Customer ID: {customer_id}"
        )

    repo = dynamodb_client.DynamoDBClient()

    # downgrade user
    repo.update_item(
        table=Config.Constants.SHEETS_API_TABLE,
        key={"id": f"user-{email}"},
        item={"premium": False},
    )

    # freeze all but the first three APIs
    sheets = google_sheets_client.get_sheets_for_email(email=email)
    sorted_sheets = sorted(sheets, key=lambda item: item["created_at"])
    all_but_last_three_sheets = sorted_sheets[:-3]
    for sheet in all_but_last_three_sheets:
        repo.update_item(
            Config.Constants.SHEETS_API_TABLE,
            key={"id": sheet["id"]},
            item={"frozen": True},
        )


def get_event(payload, header):
    return stripe.Webhook.construct_event(payload, header, WEBHOOK_SECRET)
