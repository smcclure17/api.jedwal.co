import dataclasses
import requests
from typing import Dict, Any, Optional
from google.oauth2.credentials import Credentials

from sheetsapi import auth_utils
from sheetsapi.models.domain_models import RefreshTokenInfo


class DocAccessException(Exception):
    """Passed when we can't get to doc"""


EMPTY_ACCESS_TOKEN = "Some Placeholder Value"  # empty strs fail the refresh


@dataclasses.dataclass
class GoogleDocs:
    """Class for interacting with Google Sheets"""

    creds: Credentials
    session: requests.Session

    @classmethod
    def from_token_info(cls, info: RefreshTokenInfo):
        """Create an instance using encrypted refresh token data, and optionally an access token

        We immediately just refresh/create a new one. This costs us a ~100ms, so not ideal but
        not worth the effort right now to optimize (by storing and juggling access keys.)
        """

        auth = auth_utils.GoogleOauthFields.from_tokens(
            access_token=EMPTY_ACCESS_TOKEN, refresh_token_info=info
        )
        auth = auth.refresh_access_token()  # eventually we should fix/skip this
        return GoogleDocs(creds=auth.google_oauth_creds, session=requests.Session())

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
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
