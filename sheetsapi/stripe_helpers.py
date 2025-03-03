import stripe
from sheetsapi import dynamodb_client, sheet_api_manager
from sheetsapi.config import Config

Config.init()
stripe.api_key = Config.Constants.STRIPE_SECRET_KEY
WEBHOOK_SECRET = Config.Constants.STRIPE_WEBHOOK_SECRET


def upgrade_user(email: str, api_manager: sheet_api_manager.SheetManager) -> None:
    """Mark a user as a premium user"""
    repo = dynamodb_client.DynamoDBClient()

    # mark as premium user
    repo.update_item(
        table=Config.Constants.SHEETS_API_TABLE,
        key={"id": f"user#{email}"},
        item={"premium": True},
    )

    # reactivate any APIs that might be frozen
    sheets = api_manager.get_sheet_apis_for_email(email=email)
    for sheet in sheets:
        repo.update_item(
            Config.Constants.SHEETS_API_TABLE,
            key={"id": sheet["id"]},
            item={"frozen": False},
        )


def downgrade_user(
    customer_id: str, api_manager: sheet_api_manager.SheetManager
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
        key={"id": f"user#{email}"},
        item={"premium": False},
    )

    # freeze all but the most recent 2 APIs
    sheets = api_manager.get_sheet_apis_for_email(email=email)
    sorted_sheets = sorted(sheets, key=lambda item: item["created_at"])
    all_but_last_two_sheets = sorted_sheets[:-2]
    for sheet in all_but_last_two_sheets:
        repo.update_item(
            Config.Constants.SHEETS_API_TABLE,
            key={"id": sheet["id"]},
            item={"frozen": True},
        )


def get_event(payload, header):
    return stripe.Webhook.construct_event(payload, header, WEBHOOK_SECRET)
