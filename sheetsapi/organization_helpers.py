import datetime
import logging
import secrets
import string
from typing import List, Optional

from sheetsapi import dynamodb_client, dynamodb_sheet_repo
from sheetsapi.config import Config
from sheetsapi.models.db_models import (
    OrganizationModel,
    OrganizationMembership,
    PartialUserModel,
)

logger = logging.getLogger(__name__)


class OrganizationNotFound(Exception):
    """Raised when the requested organization cannot be found"""


class NotOrganizationMember(Exception):
    """Raised when a user is not a member of the organization"""


def generate_org_id(length=7):
    """Generate a unique organization ID"""
    characters = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(characters) for _ in range(length))


def create_organization(name: str, user: PartialUserModel) -> OrganizationModel:
    """Create a new organization.

    Args:
        name: Name of the organization
        user: The current user session

    Returns:
        The newly created organization model
    """
    repo = dynamodb_client.DynamoDBClient()

    # Generate a unique organization ID
    org_id = generate_org_id()

    # Create the organization
    now = datetime.datetime.now().isoformat()

    org = OrganizationModel(
        PK=f"ORG#{org_id}",
        GSI1PK=f"ORG#{org_id}",
        orgId=org_id,
        name=name,
        createdAt=now,
        createdBy=user.userId,
    )

    # Create the membership for the creator (as admin)
    membership = OrganizationMembership(
        PK=user.PK,
        SK=f"ORG#{org_id}",
        GSI1PK=f"ORG#{org_id}",
        GSI1SK=user.PK,
        userId=user.userId,
        orgId=org_id,
        email=user.email,
        role="admin",  # Creator is always admin
        joinedAt=now,
    )

    # Store both records in a transaction
    repo.transact_write_items(
        [
            {
                "Put": {
                    "TableName": Config.Constants.SHEETS_API_TABLE,
                    "Item": org.model_dump(),
                }
            },
            {
                "Put": {
                    "TableName": Config.Constants.SHEETS_API_TABLE,
                    "Item": membership.model_dump(),
                }
            },
        ]
    )

    return org


def get_organization(org_id: str) -> Optional[OrganizationModel]:
    """Retrieve organization data.

    Args:
        org_id: The organization ID

    Returns:
        The organization or None if not found
    """
    repo = dynamodb_client.DynamoDBClient()
    org_data = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"PK": f"ORG#{org_id}", "SK": "#METADATA"}
    )

    if not org_data:
        return None

    return OrganizationModel(**org_data)


def get_organization_members(org_id: str) -> List[OrganizationMembership]:
    """Get all members of an organization.

    Args:
        org_id: The organization ID

    Returns:
        List of organization members
    """
    repo = dynamodb_client.DynamoDBClient()

    # Query GSI1 to get all members of the organization
    members_data = repo.query_index(
        table=Config.Constants.SHEETS_API_TABLE,
        index="GSI1",
        key="GSI1PK",
        value=f"ORG#{org_id}",
        KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :user_prefix)",
        ExpressionAttributeValues={":user_prefix": "USER#"},
    )

    return [OrganizationMembership(**item) for item in members_data]


def is_organization_member(
    org_id: str, user_id: str, client: Optional[dynamodb_client.DynamoDBClient] = None
) -> bool:
    """Check if a user is a member of the organization.

    Args:
        org_id: The organization ID
        user_id: The user ID
        client: Optional DynamoDB client

    Returns:
        True if the user is a member, False otherwise
    """
    if client is None:
        client = dynamodb_client.DynamoDBClient()

    membership = client.get_item(
        Config.Constants.SHEETS_API_TABLE,
        {"PK": f"USER#{user_id}", "SK": f"ORG#{org_id}"},
    )
    return membership is not None


def get_member_role(
    org_id: str, user_id: str, client: Optional[dynamodb_client.DynamoDBClient] = None
) -> Optional[OrganizationMembership]:
    """Get a user's membership details in an organization.
    
    Args:
        org_id: The organization ID
        user_id: The user ID
        client: Optional DynamoDB client
        
    Returns:
        The OrganizationMembership object or None if not a member
    """
    if client is None:
        client = dynamodb_client.DynamoDBClient()
    
    membership_data = client.get_item(
        Config.Constants.SHEETS_API_TABLE,
        {"PK": f"USER#{user_id}", "SK": f"ORG#{org_id}"}
    )
    
    if not membership_data:
        return None
        
    return OrganizationMembership(**membership_data)


def get_user_organizations(user_id: str) -> List[OrganizationMembership]:
    """Get all organizations a user is a member of.

    Args:
        user_id: The user ID

    Returns:
        List of organization memberships
    """
    repo = dynamodb_client.DynamoDBClient()

    # Query the base table to get all organizations the user is a member of
    memberships_data = repo.query_index(
        table=Config.Constants.SHEETS_API_TABLE,
        index=None,  # Use the base table
        key="PK",
        value=f"USER#{user_id}",
        KeyConditionExpression="PK = :pk AND begins_with(SK, :org_prefix)",
        ExpressionAttributeValues={":org_prefix": "ORG#"},
    )
    return [OrganizationMembership(**item) for item in memberships_data]


def add_user_to_organization(
    org_id: str, email: str, user_id: str, role: str = "member"
):
    """Add a user to an organization.

    Args:
        org_id: The organization ID
        email: The user's email
        user_id: The user ID
        role: The role within the organization, default is "member"
    """
    repo = dynamodb_client.DynamoDBClient()

    membership = OrganizationMembership(
        PK=f"USER#{user_id}",
        SK=f"ORG#{org_id}",
        GSI1PK=f"ORG#{org_id}",
        GSI1SK=f"USER#{user_id}",
        userId=user_id,
        orgId=org_id,
        email=email,
        role=role,
        joinedAt=datetime.datetime.now().isoformat(),
    )

    repo.put_item(Config.Constants.SHEETS_API_TABLE, membership.model_dump())


def delete_organization(
    org_id: str, user_id: str, client: dynamodb_client.DynamoDBClient = None
) -> None:
    """Delete an organization and all its memberships.

    This function will:
    1. Verify the user is an admin of the organization
    2. Get all organization members
    3. Delete all member records
    4. Delete the organization record

    Args:
        org_id: The ID of the organization to delete
        user_id: The ID of the user requesting the deletion
        client: Optional DynamoDB client. If None, a new client will be created.

    Raises:
        OrganizationNotFound: If the organization doesn't exist
        NotOrganizationMember: If the user is not an admin of the organization
    """
    if client is None:
        client = dynamodb_client.DynamoDBClient()

    # Check if the organization exists
    org = get_organization(org_id)
    if not org:
        raise OrganizationNotFound(f"Organization with ID {org_id} not found.")

    # Check if the user is an admin
    membership = client.get_item(
        Config.Constants.SHEETS_API_TABLE,
        {"PK": f"USER#{user_id}", "SK": f"ORG#{org_id}"},
    )

    if not membership:
        raise NotOrganizationMember(
            f"User {user_id} is not a member of organization {org_id}."
        )
    membership = OrganizationMembership(**membership)

    if membership.role != "admin":
        raise NotOrganizationMember(
            f"User {user_id} is not an admin of organization {org_id} and cannot delete it."
        )

    transaction_items = []

    # Delete organization item
    transaction_items.append(
        {
            "Delete": {
                "TableName": Config.Constants.SHEETS_API_TABLE,
                "Key": {"PK": f"ORG#{org_id}", "SK": "#METADATA"},
            }
        }
    )

    # Add items to delete all memberships
    members = get_organization_members(org_id)
    for member in members:
        transaction_items.append(
            {
                "Delete": {
                    "TableName": Config.Constants.SHEETS_API_TABLE,
                    "Key": {"PK": f"USER#{member.userId}", "SK": f"ORG#{org_id}"},
                }
            }
        )

    # Add items to delete all organization sheets
    sheet_repo = dynamodb_sheet_repo.DynamoDBSheetRepository(repository=client)
    sheets = sheet_repo.get_sheet_apis_for_org(org_id)
    for sheet in sheets:
        transaction_items.append(
            {
                "Delete": {
                    "TableName": Config.Constants.SHEETS_API_TABLE,
                    "Key": {"PK": f"SHEET#{sheet.apiName}", "SK": "#METADATA"},
                }
            }
        )

    # DynamoDB limits a transaction to 25 items, so we may need multiple transactions
    # Process in batches of 25
    batch_size = 25
    for i in range(0, len(transaction_items), batch_size):
        batch = transaction_items[i : i + batch_size]
        client.transact_write_items(batch)

    logger.info(
        f"Organization {org_id}, {len(members)} memberships, and {len(sheets)} sheets have been deleted."
    )
