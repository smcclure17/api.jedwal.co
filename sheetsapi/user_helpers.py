from typing import Any, Iterable, Optional
import logging

from sheetsapi import sheet_api_repo_v2
from sheetsapi.config import Config
from sheetsapi.models.domain_models import UserSession

logger = logging.getLogger(__name__)


def persist_user_if_not_exists(
    user: UserSession, client: Optional[sheet_api_repo_v2.SheetApiRepo] = None
):
    """Store a user (not organization) in the database if one does not already exist"""
    if client is None:
        client = sheet_api_repo_v2.SheetApiRepo.from_table_name(
            table_name=Config.Constants.SHEETS_API_TABLE
        )

    existing_user = client.get_account(user.sub)
    if existing_user:
        return existing_user["account_id"]

    logger.info(f"Creating new user for email: {user.email}")
    item = client.create_user(
        user_id=user.sub,
        email=user.email,
        refresh_token=user.refresh_token,
        given_name=user.given_name,
        family_name=user.family_name,
    )
    return item["account_id"]
