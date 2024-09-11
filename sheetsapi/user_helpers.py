from typing import Iterable
import logging

from fastapi import Request
from sheetsapi import dynamodb_client
from sheetsapi.config import Config

logger = logging.getLogger(__name__)


def persist_user_if_not_exists(user: dict, request: Request) -> None:
    """Persist a user in the repository if they do not already exist.

    Args:
        user (dict): The user to persist.
        request (Request): The request object.
    """

    email = user.get("email")
    if email is None:
        logger.error(f"User does not have an email. Cannot persist. User: {user}")
        return

    session = request.session
    user_model = {
        **user,
        "id": f"user-{email}",
        "refresh_token": session.get("refresh_token"),
        "api_count": 0,
    }

    repo = dynamodb_client.DynamoDBClient()
    user_item = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"id": f"user-{email}"}
    )

    if user_item is None:
        logger.info(f"User with email {email} not found in repository. Adding them.")
        repo.put_item(Config.Constants.SHEETS_API_TABLE, user_model)


def fetch_fields_for_user(email: str, fields: Iterable[str]) -> str:
    """Fetch and select fields from a user in the repository.

    Args:
        email (str): The email address of the user.
        fields: Values to retrieve from the user item

    Returns:
        dict: Key value pairs of requested fields
    """

    repo = dynamodb_client.DynamoDBClient()
    user_item = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"id": f"user-{email}"}
    )
    if user_item is None:
        return None

    res = {}
    for key in fields:
        if not key in user_item:
            raise ValueError(f"Request field '{key}' does not exist in user object.")
        res[key] = user_item[key]
    return res
