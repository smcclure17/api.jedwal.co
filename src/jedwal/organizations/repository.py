from datetime import UTC, datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.common.exceptions import ConflictException, NotFoundException
from jedwal.organizations.models import Organization


def to_organization(*, item: dict):
    updated_stamp = item.get("updated_at", datetime.now().isoformat())
    return Organization(
        account_id=item["account_id"],
        account_status="premium",
        billing_account_id=item["billing_account_id"],
        display_name=item["display_name"],
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(updated_stamp),
    )


def to_item(*, org: Organization):
    return {
        "PK": f"ACCOUNT#{org.account_id}",
        "SK": f"ACCOUNT#{org.account_id}",
        "type": "organization",
        "account_id": org.account_id,
        "display_name": org.display_name,
        "account_status": "premium",
        "created_by": org.billing_account_id,
        "billing_account_id": org.billing_account_id,
        "created_at": org.created_at.isoformat(),
        "updated_at": org.updated_at.isoformat(),
    }


def get_organization(*, table: Table, id: str) -> Organization | None:
    response = table.get_item(Key={"PK": f"ACCOUNT#{id}", "SK": f"ACCOUNT#{id}"})
    item = response.get("Item", None)
    if item is None or item["type"] != "organization":
        return None
    return to_organization(item=item)


def create_organization(*, table: Table, org: Organization) -> Organization:
    """Create a new org in the db."""
    item = to_item(org=org)

    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictException(
                f"Account or Org with account_id {org.account_id} already exists"
            ) from e
        raise

    return org


def update_organization(*, table: Table, organization: Organization) -> Organization:
    organization.updated_at = datetime.now(UTC)

    item = to_item(org=organization)

    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_exists(PK) AND #type = :org_type",
            ExpressionAttributeNames={"#type": "type"},
            ExpressionAttributeValues={":org_type": "organization"},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(
                f"Organization with account_id {organization.account_id} not found"
            ) from e
        raise

    return organization


def delete_organization(*, table: Table, account_id: str) -> None:
    try:
        table.delete_item(
            Key={
                "PK": f"ACCOUNT#{account_id}",
                "SK": f"ACCOUNT#{account_id}",
            },
            ConditionExpression="attribute_exists(PK) AND #type = :org_type",
            ExpressionAttributeNames={"#type": "type"},
            ExpressionAttributeValues={":org_type": "organization"},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(
                f"Organization with id {account_id} not found"
            ) from e
        raise
