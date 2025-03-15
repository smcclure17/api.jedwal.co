import dataclasses
import logging
import gspread
from sheetsapi import envelope_encryption
from sheetsapi.config import Config
from google.oauth2.credentials import Credentials

from sheetsapi.models.domain_models import RefreshTokenInfo


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

    access_token: str
    refresh_token_info: RefreshTokenInfo
    token_uri: str
    client_id: str
    client_secret: str

    @classmethod
    def from_tokens(
        cls, access_token: str, refresh_token_info: RefreshTokenInfo
    ) -> "GoogleOauthFields":
        """Create instance from access and refresh tokens and other default values.

        Args:
            access_token: Access token for the oauth session.
            refresh_token: Refresh token for the oauth session.

        Returns:
            Instance of GoogleOauthFields.
        """

        return cls(
            access_token=access_token,
            refresh_token_info=refresh_token_info,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=Config.Constants.GOOGLE_CLIENT_ID,
            client_secret=Config.Constants.GOOGLE_CLIENT_SECRET,
        )

    def init_gspread_client(self) -> gspread.Client:
        """Initialize a gspread client with the oauth fields.

        Returns:
            gspread.Client: The gspread client.
        """

        # Decrypt refresh_token right before sending off to Google
        refresh_token = envelope_encryption.EnvelopeEncryption.decrypt(
            encrypted_data_b64=self.refresh_token_info.encrypted_refresh_token,
            encrypted_key_b64=self.refresh_token_info.data_encryption_key,
            context=self.refresh_token_info.context,
        )

        creds = Credentials(
            token=self.access_token,
            refresh_token=refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        return gspread.authorize(creds)
