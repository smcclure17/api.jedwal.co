from typing import Any, Optional
import logging

from sheetsapi import envelope_encryption
from sheetsapi.sheet_api_repo_v2 import SheetApiRepo
from sheetsapi.models.domain_models import RefreshTokenInfo, UserSession

logger = logging.getLogger(__name__)


def persist_user(
    user: UserSession, refresh_token: str, sheet_repo: Optional[SheetApiRepo] = None
):
    """Store a user in the database if one does not already exist"""
    if sheet_repo is None:
        sheet_repo = SheetApiRepo.from_table_name()

    encryption_response = envelope_encryption.EnvelopeEncryption.encrypt(
        refresh_token, context={"account_id": user.sub}
    )

    token_info = RefreshTokenInfo(
        encrypted_refresh_token=encryption_response.encrypted_data,
        data_encryption_key=encryption_response.encrypted_key,
        context=encryption_response.context,
    )

    item = sheet_repo.create_user(
        user_id=user.sub,
        email=user.email,
        given_name=user.given_name,
        family_name=user.family_name,
        refresh_token_info=token_info,
    )
    return item["account_id"]
