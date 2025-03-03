from typing import Iterable
import logging
import secrets
import string

from sheetsapi import dynamodb_client
from sheetsapi.config import Config

logger = logging.getLogger(__name__)


class UserNotFound(Exception):
    """Raised when a user with the given information cannot be found"""


def lookup_user_by_email(
    email: str, client: dynamodb_client.DynamoDBClient | None = None
):
    """Lookup a user with by a given email"""
    if client is None:
        client = dynamodb_client.DynamoDBClient()
    existing_user = client.get_item(
        Config.Constants.SHEETS_API_TABLE, {"PK": f"EMAIL#{email}", "SK": "#LOOKUP"}
    )
    if not existing_user:
        raise UserNotFound(f"User with email {email} not found.")
    return existing_user


def persist_user_if_not_exists(user: dict, refresh_token: str) -> None:
    email = user.get("email")
    if email is None:
        logger.error(f"User does not have an email. Cannot persist. User: {user}")
        return

    repo = dynamodb_client.DynamoDBClient()
    try:
        existing_user = lookup_user_by_email(email, repo)
    except UserNotFound:
        existing_user = None

    def generate_id(length=7):
        characters = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(characters) for _ in range(length))

    user_id = generate_id()

    if not existing_user:
        logger.info(f"User with email {email} not found in repository. Adding them.")
        email_lookup = {
            "PK": f"EMAIL#{email}",
            "SK": "#LOOKUP",
            "GSI1PK": f"USER#{user_id}",
            "userId": user_id,
        }
        user_model = {
            # Primary keys
            "PK": f"USER#{user_id}",  # Using generated ID instead of email
            "SK": "#PROFILE",
            # User attributes
            "userId": user_id,
            "email": email,
            "refreshToken": refresh_token,
            "apiCount": 0,
            "premium": False,
            # Copy other user attributes
            "name": user.get("name"),
            "givenName": user.get("given_name"),
            "familyName": user.get("family_name"),
            "picture": user.get("picture"),
            "emailVerified": user.get("email_verified"),
        }

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


def fetch_fields_for_user(email: str, fields: Iterable[str]) -> str:
    """Fetch and select fields from a user in the repository.

    Args:
        email (str): The email address of the user.
        fields: Values to retrieve from the user item

    Returns:
        dict: Key value pairs of requested fields
    """
    repo = dynamodb_client.DynamoDBClient()

    # First get the userId from email lookup
    email_lookup = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"PK": f"EMAIL#{email}", "SK": "#LOOKUP"}
    )
    if email_lookup is None:
        return None

    user_id = email_lookup["userId"]
    user_item = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"PK": f"USER#{user_id}", "SK": "#PROFILE"}
    )

    if user_item is None:
        return None

    res = {}
    for key in fields:
        # Add mapping for field name changes
        field_mapping = {
            "user_id": "userId",
            "refresh_token": "refreshToken",
            "api_count": "apiCount",
            "given_name": "givenName",
            "family_name": "familyName",
            "email_verified": "emailVerified",
        }

        mapped_key = field_mapping.get(key, key)
        if mapped_key not in user_item:
            raise ValueError(f"Requested field '{key}' does not exist in user object.")
        res[key] = user_item[mapped_key]  # Keep original key in response
    return res
