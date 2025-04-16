import dataclasses
from functools import cached_property

import gspread
from sheetsapi import auth_utils
from sheetsapi.models.domain_models import RefreshTokenInfo, SpreadsheetDataModel


class InaccessibleDocument(Exception):
    "Raised when a Google Sheet cannot be opened, e.g., if it's actually an XLSX"


class NonUniqueColumnsError(Exception):
    """Raised when e.g. a Google sheet has non-unique column names."""


class InsufficientPermissions(Exception):
    """Raised when the user does not have access to the sheet"""


EMPTY_ACCESS_TOKEN = "Some Placeholder Value"  # empty strs fail the refresh


@dataclasses.dataclass
class GoogleSheets:
    """Class for interacting with Google Sheets"""

    auth_creds: auth_utils.GoogleOauthFields

    @classmethod
    def from_token_info(cls, info: RefreshTokenInfo):
        """Create an instance using encrypted refresh token data, and optionally an access token

        We immediately just refresh/create a new one. This costs us a ~100ms, so not ideal but
        not worth the effort right now to optimize (by storing and juggling access keys.)
        """

        auth_creds = auth_utils.GoogleOauthFields.from_tokens(
            access_token=EMPTY_ACCESS_TOKEN, refresh_token_info=info
        )
        return GoogleSheets(auth_creds=auth_creds)

    @cached_property
    def gspread_client(self):
        return self.auth_creds.init_gspread_client()

    def get_spreadsheet_data(self, sheet_id: str) -> SpreadsheetDataModel:
        google_sheet = self._try_open_spreadsheet(sheet_id=sheet_id)
        return SpreadsheetDataModel(
            id=google_sheet.id,
            title=google_sheet.title,
            worksheets=[worksheet.title for worksheet in google_sheet.worksheets()],
        )

    @staticmethod
    def get_worksheet_data(worksheet: gspread.worksheet.Worksheet):
        try:
            return worksheet.get_all_records()
        except gspread.exceptions.GSpreadException as error:
            if str(error).startswith("the header row in the worksheet is not unique"):
                raise NonUniqueColumnsError("Spreadsheet columns are not unique")
            raise error


    def get_worksheet_by_name(self, sheet_id, name):
        return self._try_open_spreadsheet(sheet_id).worksheet(name)

    def _try_open_spreadsheet(self, sheet_id: str):
        try:
            google_sheet = self.gspread_client.open_by_key(sheet_id)
        except gspread.exceptions.APIError as e:
            # can't use get_file_drive_metadata b/c we'd need to add more auth scopes
            # parse the error to find out if it's a non-supported file.
            message = e.error["message"]
            if message == "This operation is not supported for this document":
                raise InaccessibleDocument("Filetype is unsupported")
            if message == "The caller does not have permission":
                raise InsufficientPermissions("User does not have access to file")
            raise e
        except PermissionError:
            raise InsufficientPermissions("User does not have access to file")
        return google_sheet
