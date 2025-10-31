"""OAuth configuration for Google authentication."""

from authlib.integrations.starlette_client import OAuth

from jedwal.config.config import settings

# OAuth scopes for Google Drive and user profile
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "openid",
    "profile",
    "email",
]

OAUTH_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Initialize OAuth client
oauth = OAuth()

# Register Google OAuth provider
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url=OAUTH_METADATA_URL,
    client_kwargs={"scope": " ".join(OAUTH_SCOPES)},
)
