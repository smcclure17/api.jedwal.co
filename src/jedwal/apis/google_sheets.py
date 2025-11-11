import gspread

from jedwal.account.models import RefreshTokenInfo
from jedwal.common.google_auth_fields import GoogleOauthFields


class InaccessibleDocument(Exception):
    "Raised when a Google Sheet cannot be opened, e.g., if it's actually an XLSX"


class NonUniqueColumnsError(Exception):
    """Raised when e.g. a Google sheet has non-unique column names."""


class InsufficientPermissions(Exception):
    """Raised when the user does not have access to the sheet"""


class GoogleRateLimitExceeded(Exception):
    """Raised when user exceeds their Google Sheets quota"""


def open_spreadsheet(
    *, gspread_client: gspread.Client, sheet_id: str
) -> gspread.Spreadsheet:
    try:
        google_sheet = gspread_client.open_by_key(sheet_id)
    except gspread.exceptions.APIError as e:
        # can't use get_file_drive_metadata b/c we'd need to add more auth scopes
        # parse the error to find out if it's a non-supported file.
        message = e.error["message"]
        if message == "This operation is not supported for this document":
            raise InaccessibleDocument("Filetype is unsupported") from e
        if message == "The caller does not have permission":
            raise InsufficientPermissions("User does not have access to file") from e
        if e.code == 429:
            raise GoogleRateLimitExceeded(
                "Google Sheets Rate Limit exceeded (error 429)."
            ) from e
        raise e
    except PermissionError as e:
        raise InsufficientPermissions("User does not have access to file") from e
    return google_sheet


def read_worksheet(*, worksheet: gspread.Worksheet) -> list[dict]:
    try:
        return worksheet.get_all_records()
    except gspread.exceptions.GSpreadException as error:
        if str(error).startswith("the header row in the worksheet is not unique"):
            raise NonUniqueColumnsError("Spreadsheet columns are not unique") from error
        if str(error).startswith("the header row in the worksheet contains duplicates"):
            raise NonUniqueColumnsError("Spreadsheet columns are not unique") from error
        raise error


def gspread_from_refresh_token_info(
    *, refresh_token_info: RefreshTokenInfo
) -> gspread.Client:
    google_oauth_fields = GoogleOauthFields.from_tokens(
        access_token="some access token",  # force a refresh. TODO: can we avoid this?
        refresh_token_info=refresh_token_info,
    )
    return gspread.authorize(google_oauth_fields.google_oauth_creds)
