import dataclasses
import logging
from functools import cached_property

import requests
from google.oauth2.credentials import Credentials

from jedwal.account.models import RefreshTokenInfo
from jedwal.common.encryption.service import EncryptionService
from jedwal.config import settings

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class GoogleOauthFields:
    """Fields needed for Google OAuth.

    Args:
        access_token: Access token for the oauth session.
        refresh_token_info: Encrypted refresh token, DEK and context for decrypting.
        token_uri: Token URI.
        client_id: Auth app client ID.
        client_secret: Auth app client secret.
    """

    encryption: EncryptionService
    access_token: str
    refresh_token_info: RefreshTokenInfo
    token_uri: str
    client_id: str
    client_secret: str

    @cached_property
    def google_oauth_creds(self):
        refresh_token = self.encryption.decrypt(
            encrypted_data=self.refresh_token_info.encrypted_refresh_token,
            encrypted_key=self.refresh_token_info.data_encryption_key,
            context=self.refresh_token_info.context,
        )

        return Credentials(
            token=self.access_token,
            refresh_token=refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

    @classmethod
    def from_tokens(
        cls,
        encryption: EncryptionService,
        access_token: str,
        refresh_token_info: RefreshTokenInfo,
    ) -> "GoogleOauthFields":
        """Create instance from access and refresh tokens and other default values.

        Args:
            access_token: Access token for the oauth session.
            refresh_token: Refresh token for the oauth session.

        Returns:
            Instance of GoogleOauthFields.
        """

        return cls(
            encryption=encryption,
            access_token=access_token,
            refresh_token_info=refresh_token_info,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )

    def refresh_access_token(self) -> "GoogleOauthFields":
        """Refresh the access token using the stored refresh token."""
        refresh_token = self.encryption.decrypt(
            encrypted_data=self.refresh_token_info.encrypted_refresh_token,
            encrypted_key=self.refresh_token_info.data_encryption_key,
            context=self.refresh_token_info.context,
        )

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        response = requests.post(self.token_uri, data=payload)

        if not response.ok:
            logger.error(f"Failed to refresh token: {response.text}")
            raise Exception(f"Failed to refresh token: {response.text}")

        token_response = response.json()
        new_access_token = token_response["access_token"]

        return GoogleOauthFields(
            access_token=new_access_token,
            refresh_token_info=self.refresh_token_info,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
