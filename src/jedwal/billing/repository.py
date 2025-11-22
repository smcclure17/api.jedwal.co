"""Billing repository for DynamoDB operations."""

from datetime import datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import AccountId
from jedwal.billing.models import BillingInfo
from jedwal.common.exceptions import NotFoundException


def to_billing_item(*, billing_info: BillingInfo) -> dict:
    """Convert billing domain model to DynamoDB update fields.

    Note: This returns partial item data for updates, not a full item.
    """
    item = {}

    if billing_info.billing_start:
        item["billing_start"] = billing_info.billing_start.isoformat()

    if billing_info.billing_end:
        item["billing_end"] = billing_info.billing_end.isoformat()
        # GSI4 for querying accounts by billing end date
        item["GSI4PK"] = (
            f"ACCOUNT#BILLING_END#{billing_info.billing_end.date().isoformat()}"
        )

    if billing_info.stripe_customer_id:
        item["stripe_customer_id"] = billing_info.stripe_customer_id

    if billing_info.stripe_subscription_id:
        item["stripe_subscription_id"] = billing_info.stripe_subscription_id

    return item


def to_billing_info(*, item: dict) -> BillingInfo:
    """Convert DynamoDB item to billing domain model.

    Extracts only billing-related fields from the account item.
    """
    return BillingInfo(
        account_id=item["account_id"],
        billing_start=(
            datetime.fromisoformat(item["billing_start"])
            if item.get("billing_start")
            else None
        ),
        billing_end=(
            datetime.fromisoformat(item["billing_end"])
            if item.get("billing_end")
            else None
        ),
        stripe_customer_id=item.get("stripe_customer_id"),
        stripe_subscription_id=item.get("stripe_subscription_id"),
    )


def get_billing_info(*, table: Table, account_id: AccountId) -> BillingInfo | None:
    """Get billing information for an account."""
    response = table.get_item(
        Key={"PK": f"ACCOUNT#{account_id}", "SK": f"ACCOUNT#{account_id}"}
    )
    item = response.get("Item")

    if not item:
        return None

    return to_billing_info(item=item)


def update_billing_info(*, table: Table, billing_info: BillingInfo) -> BillingInfo:
    """Update billing information for an account.

    Args:
        table: DynamoDB table resource
        billing_info: Billing info with updates

    Returns:
        Updated billing info

    Raises:
        NotFoundException: If account not found
    """
    item_updates = to_billing_item(billing_info=billing_info)

    if not item_updates:
        # No fields to update
        return billing_info

    # Build update expression dynamically
    update_parts = []
    expression_values = {}

    for key, value in item_updates.items():
        update_parts.append(f"{key} = :{key}")
        expression_values[f":{key}"] = value

    update_expression = "SET " + ", ".join(update_parts)

    try:
        table.update_item(
            Key={
                "PK": f"ACCOUNT#{billing_info.account_id}",
                "SK": f"ACCOUNT#{billing_info.account_id}",
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(
                f"Account with id {billing_info.account_id} not found"
            ) from e
        raise

    return billing_info


def get_accounts_by_billing_end_date(
    *, table: Table, billing_end_date: str
) -> list[BillingInfo]:
    """Get billing info for all accounts whose billing period ends on specified date.

    Args:
        table: DynamoDB table
        billing_end_date: Date in YYYY-MM-DD format

    Returns:
        List of BillingInfo objects
    """
    response = table.query(
        IndexName="GSI4",
        KeyConditionExpression="GSI4PK = :billing_pk",
        ExpressionAttributeValues={
            ":billing_pk": f"ACCOUNT#BILLING_END#{billing_end_date}"
        },
    )

    items = response.get("Items", [])
    return [to_billing_info(item=item) for item in items]
