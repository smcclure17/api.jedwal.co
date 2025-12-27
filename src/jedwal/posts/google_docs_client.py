import dataclasses
from typing import Any

import requests
from google.oauth2.credentials import Credentials

from jedwal.account.models import RefreshTokenInfo
from jedwal.common.encryption.service import EncryptionService
from jedwal.common.google_auth_fields import GoogleOauthFields


class DocAccessException(Exception):
    """Raised when we can't get to doc"""


EMPTY_ACCESS_TOKEN = "Some Placeholder Value"  # empty strs fail the refresh


@dataclasses.dataclass
class GoogleDocs:
    """Class for interacting with Google Sheets"""

    encryption: EncryptionService
    creds: Credentials
    session: requests.Session

    @classmethod
    def from_token_info(cls, info: RefreshTokenInfo, encryption: EncryptionService):
        """Create an instance using encrypted refresh token data, and optionally an access token

        We immediately just refresh/create a new one. This costs us a ~100ms, so not ideal but
        not worth the effort right now to optimize (by storing and juggling access keys.)
        """

        auth = GoogleOauthFields.from_tokens(
            encryption=encryption,
            access_token=EMPTY_ACCESS_TOKEN,
            refresh_token_info=info,
        )
        auth = auth.refresh_access_token()  # eventually we should fix/skip this
        return GoogleDocs(creds=auth.google_oauth_creds, session=requests.Session())

    @classmethod
    def from_auth(cls, auth: GoogleOauthFields):
        return GoogleDocs(creds=auth.google_oauth_creds, session=requests.Session())

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        url = f"https://docs.googleapis.com/v1/documents/{doc_id}"
        response = self.session.get(
            url,
            headers={
                "Authorization": f"Bearer {self.creds.token}",
                "Content-Type": "application/json",
            },
        )

        if response.status_code != 200:
            raise DocAccessException(f"{response.status_code}: {response.text}")
        return response.json()
