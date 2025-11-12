from datetime import UTC, datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import Account, RefreshTokenInfo
from jedwal.common.exceptions import ConflictException, NotFoundException
from jedwal.organizations.models import Organization
from jedwal.organizations.repository import to_organization


def to_item(*, account: Account) -> dict:
    """Convert domain model to DynamoDB item with keys."""

    return {
        "PK": f"ACCOUNT#{account.account_id}",
        "SK": f"ACCOUNT#{account.account_id}",
        "type": "user",
        "account_id": account.account_id,
        "display_name": account.display_name,
        "email": account.email,
        "refresh_token_info": account.refresh_token_info.to_dict(),
        "given_name": account.given_name,
        "family_name": account.family_name,
        "account_status": account.account_status,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
        "do_not_email": account.do_not_email,
        # GSI3 for looking up accounts by email
        "GSI3PK": f"EMAIL#{account.email.lower()}",
        "GSI3SK": f"ACCOUNT#{account.account_id}",
    }


def to_account(*, item: dict) -> Account:
    """Convert DynamoDB item to account model."""
    # updated at might not exist in db, so just set it if not
    updated_stamp = item.get("updated_at", datetime.now().isoformat())

    return Account(
        account_id=item["account_id"],
        email=item["email"],
        display_name=item["display_name"],
        given_name=item.get("given_name"),
        family_name=item.get("family_name"),
        account_status=item["account_status"],
        refresh_token_info=RefreshTokenInfo(**item["refresh_token_info"]),
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(updated_stamp),
        do_not_email=item.get("do_not_email", False),
    )


def create_account(*, table: Table, account: Account) -> Account:
    """
    Create a new account in the db.

    Args:
        account: account domain model to create
        table: DynamoDB table resource (injected for testing)

    Returns:
        Created account

    Raises:
        ConflictException: If account already exists
    """
    item = to_item(account=account)

    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictException(
                f"Account with account_id {account.account_id} already exists"
            ) from e
        raise

    return account


def update_account(*, table: Table, account: Account) -> Account:
    """
    Update an existing account.

    Args:
        table: DynamoDB table resource (injected for testing)
        account: Account domain model with updates

    Returns:
        Updated account

    Raises:
        NotFoundException: If account not found
    """
    # Update the updated_at timestamp
    account.updated_at = datetime.now(UTC)

    item = to_item(account=account)

    try:
        table.put_item(Item=item, ConditionExpression="attribute_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(
                f"Account with account_id {account.account_id} not found"
            ) from e
        raise

    return account


def delete_account(*, table: Table, account_id: str) -> None:
    """
    Delete an account from the db.

    Args:
        account_id: Account ID to delete
        table: DynamoDB table resource (injected for testing)

    Raises:
        NotFoundException: If account not found
    """
    try:
        table.delete_item(
            Key={
                "PK": f"ACCOUNT#{account_id}",
                "SK": f"ACCOUNT#{account_id}",
            },
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(f"Account with id {account_id} not found") from e
        raise


def get_account(*, table: Table, id: str) -> Account | None:
    response = table.get_item(Key={"PK": f"ACCOUNT#{id}", "SK": f"ACCOUNT#{id}"})
    item = response.get("Item", None)
    # TODO: we should prob pull apart accounts from orgs in the db
    if item is None or item["type"] != "user":
        return None
    return to_account(item=item)


def get_account_by_email(*, table: Table, email: str) -> Account:
    response = table.query(
        IndexName="GSI3",
        KeyConditionExpression="GSI3PK = :email_pk",
        ExpressionAttributeValues={":email_pk": f"EMAIL#{email.lower()}"},
    )

    items = response.get("Items", [])
    if not items:
        raise NotFoundException(f"User with email {email} not found.") from None

    return to_account(item=items[0])


def get_account_or_organization(
    *, table: Table, id: str
) -> Account | Organization | None:
    response = table.get_item(Key={"PK": f"ACCOUNT#{id}", "SK": f"ACCOUNT#{id}"})
    item = response.get("Item", None)
    if item is None:
        return None

    if item["type"] == "user":
        return to_account(item=item)
    if item["type"] == "organization":
        return to_organization(item=item)
    raise ValueError(f"Unknown account type {item['type']}") from None
