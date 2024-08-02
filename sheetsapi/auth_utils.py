import dataclasses
import logging
from fastapi import Request
import gspread
from sheetsapi import dynamodb_client
from sheetsapi.config import Config
from google.oauth2.credentials import Credentials


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
    }

    repo = dynamodb_client.DynamoDBClient()
    user_item = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"id": f"user-{email}"}
    )

    if user_item is None:
        logger.info(f"User with email {email} not found in repository. Adding them.")
        repo.put_item(Config.Constants.SHEETS_API_TABLE, user_model)


def fetch_refresh_token_for_user(email: str) -> str:
    """Fetch the refresh token for a user from the repository.

    Args:
        email (str): The email address of the user.

    Returns:
        str: The refresh token.
    """

    repo = dynamodb_client.DynamoDBClient()
    user_item = repo.get_item(
        Config.Constants.SHEETS_API_TABLE, {"id": f"user-{email}"}
    )
    return user_item.get("refresh_token") if user_item else None


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
