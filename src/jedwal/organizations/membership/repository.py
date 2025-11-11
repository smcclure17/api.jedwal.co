from datetime import datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.common.exceptions import NotFoundException
from jedwal.organizations.membership.models import Membership


def to_item(*, membership: Membership) -> dict:
    return {
        "PK": f"ACCOUNT#{membership.organization_id}",
        "SK": f"MEMBERSHIP#{membership.account_id}",
        "user_id": membership.account_id,
        "org_id": membership.organization_id,
        "member_type": membership.member_type,
        "joined_at": membership.joined_at.isoformat(),
        "GSI1PK": f"MEMBERSHIP#{membership.account_id}",
        "GSI1SK": f"ACCOUNT#{membership.organization_id}",
    }


def to_membership(*, item: dict) -> Membership:
    return Membership(
        account_id=item["user_id"],
        organization_id=item["org_id"],
        member_type=item["member_type"],
        joined_at=datetime.fromisoformat(item["joined_at"]),
    )


def create_memberships(
    *, table: Table, memberships: list[Membership]
) -> list[Membership]:
    with table.batch_writer() as batch:
        for membership in memberships:
            item = to_item(membership=membership)
            batch.put_item(Item=item)
    return memberships


def delete_membership(*, table: Table, account_id: str, organization_id: str) -> None:
    try:
        table.delete_item(
            Key={
                "PK": f"ACCOUNT#{organization_id}",
                "SK": f"MEMBERSHIP#{account_id}",
            },
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundException(
                f"Membership for account {account_id} in org {organization_id} not found"
            ) from e
        raise


def get_membership(
    *, table: Table, account_id: str, organization_id: str
) -> Membership | None:
    response = table.get_item(
        Key={
            "PK": f"ACCOUNT#{organization_id}",
            "SK": f"MEMBERSHIP#{account_id}",
        }
    )
    item = response.get("Item")
    if item is None:
        return None
    return to_membership(item=item)


def get_memberships_for_org(*, table: Table, organization_id: str) -> list[Membership]:
    response = table.query(
        KeyConditionExpression="PK = :org_pk AND begins_with(SK, :membership_prefix)",
        ExpressionAttributeValues={
            ":org_pk": f"ACCOUNT#{organization_id}",
            ":membership_prefix": "MEMBERSHIP#",
        },
    )
    items = response.get("Items", [])
    return [to_membership(item=item) for item in items]


def get_memberships_for_account(*, table: Table, account_id: str) -> list[Membership]:
    response = table.query(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :membership_pk AND begins_with(GSI1SK, :account_prefix)",
        ExpressionAttributeValues={
            ":membership_pk": f"MEMBERSHIP#{account_id}",
            ":account_prefix": "ACCOUNT#",
        },
    )
    items = response.get("Items", [])
    return [to_membership(item=item) for item in items]
