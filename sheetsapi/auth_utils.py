import dataclasses
import logging
import gspread
from sheetsapi.config import Config
from google.oauth2.credentials import Credentials


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class GoogleOauthFields:
    """Fields needed for Google OAuth.

    Args:
        access_token: Access token for the oauth session.
        refresh_token: Refresh token for the oauth session.
        token_uri: Token URI.
        client_id: Auth app client ID.
        client_secret: Auth app client secret.
    """

    access_token: str
    refresh_token: str
    token_uri: str
    client_id: str
    client_secret: str

    @classmethod
    def from_tokens(cls, access_token: str, refresh_token: str) -> "GoogleOauthFields":
        """Create instance from access and refresh tokens and other default values.

        Args:
            access_token: Access token for the oauth session.
            refresh_token: Refresh token for the oauth session.

        Returns:
            Instance of GoogleOauthFields.
        """
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=Config.Constants.GOOGLE_CLIENT_ID,
            client_secret=Config.Constants.GOOGLE_CLIENT_SECRET,
        )

    def init_gspread_client(self) -> gspread.Client:
        """Initialize a gspread client with the oauth fields.

        Returns:
            gspread.Client: The gspread client.
        """
        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        return gspread.authorize(creds)
