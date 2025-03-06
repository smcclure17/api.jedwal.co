from typing import Any, Iterable
import logging
import secrets
import string

from sheetsapi import dynamodb_client
from sheetsapi.config import Config
from sheetsapi.models.db_models import PartialUserModel, UserModel, UserLookup
from sheetsapi.models.domain_models import UserSession

logger = logging.getLogger(__name__)


class UserNotFound(Exception):
    """Raised when a user with the given information cannot be found"""


def lookup_user_id_by_email(
    email: str, client: dynamodb_client.DynamoDBClient | None = None
) -> str:
    """Lookup a user with by a given email"""
    if client is None:
        client = dynamodb_client.DynamoDBClient()
    existing_user = client.get_item(
        Config.Constants.SHEETS_API_TABLE, {"PK": f"EMAIL#{email}", "SK": "#LOOKUP"}
    )
    if not existing_user:
        raise UserNotFound(f"User with email {email} not found.")
    return existing_user["userId"]


def persist_user_if_not_exists(user: UserSession) -> str | None:
    repo = dynamodb_client.DynamoDBClient()
    try:
        existing_user = lookup_user_id_by_email(user.email, repo)
    except UserNotFound:
        existing_user = None

    def generate_id(length=7):
        characters = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(characters) for _ in range(length))

    user_id = generate_id()

    if not existing_user:
        logger.info(
            f"User with email {user.email} not found in repository. Adding them."
        )
        email_lookup = UserLookup(
            PK=f"EMAIL#{user.email}",
            SK="#LOOKUP",
            userId=user_id,
        ).model_dump()

        user_model = UserModel(
            PK=f"USER#{user_id}",
            SK="#PROFILE",
            userId=user_id,
            email=user.email,
            refreshToken=user.refresh_token,
            apiCount=0,
            premium=False,
            name=user.name,
            givenName=user.given_name,
            familyName=user.family_name,
            picture=user.picture,
            emailVerified=user.email_verified,
        ).model_dump()

        # Use transaction to write both items
        repo.transact_write_items(
            [
                {
                    "Put": {
                        "TableName": Config.Constants.SHEETS_API_TABLE,
                        "Item": user_model,
                    }
                },
                {
                    "Put": {
                        "TableName": Config.Constants.SHEETS_API_TABLE,
                        "Item": email_lookup,
                    }
                },
            ]
        )
        return user_id


def fetch_fields_for_user(email: str, fields: Iterable[str]) -> PartialUserModel:
    """Fetch and select fields from a user in the repository.

    Args:
        email (str): The email address of the user.
        fields: Values to retrieve from the user item

    Returns:
        dict: Key value pairs of requested fields
    """
    repo = dynamodb_client.DynamoDBClient()

    try:
        user_id = lookup_user_id_by_email(email)
    except UserNotFound:
        return None

    user_item = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"PK": f"USER#{user_id}", "SK": "#PROFILE"}
    )
    if user_item is None:
        return None

    res = {}
    for key in fields:
        if key not in user_item:
            raise ValueError(f"Requested field '{key}' does not exist in user object.")
        res[key] = user_item[key]

    return PartialUserModel(**res)


def delete_user(email: str, client: dynamodb_client.DynamoDBClient = None) -> None:
    """Delete a user from the database.

    This function removes both the user profile and the email lookup in a transaction.

    Args:
        user_id: The ID of the user to delete
        client: Optional DynamoDB client. If None, a new client will be created.

    Raises:
        UserNotFound: If the user doesn't exist
    """
    if client is None:
        client = dynamodb_client.DynamoDBClient()

    # First get the user to find their email
    user_id = lookup_user_id_by_email(email, client=client)
    if user_id is None:
        raise UserNotFound(f"User with ID {user_id}, email {email} not found.")

    client.transact_write_items(
        [
            {
                "Delete": {
                    "TableName": Config.Constants.SHEETS_API_TABLE,
                    "Key": {"PK": f"USER#{user_id}", "SK": "#PROFILE"},
                }
            },
            {
                "Delete": {
                    "TableName": Config.Constants.SHEETS_API_TABLE,
                    "Key": {"PK": f"EMAIL#{email}", "SK": "#LOOKUP"},
                }
            },
        ]
    )

    logger.info(f"User {user_id} with email {email} has been deleted.")
