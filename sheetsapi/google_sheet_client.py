import dataclasses
from functools import cached_property

import gspread
from sheetsapi import auth_utils


class InaccessibleDocument(Exception):
    "Raised when a Google Sheet cannot be opened, e.g., if it's actually an XLSX"


@dataclasses.dataclass
class GoogleSheets:
    """Class for interacting with Google Sheets"""

    auth_creds: auth_utils.GoogleOauthFields

    @classmethod
    def from_creds_dict(cls, creds_dict: dict):
        auth_creds = auth_utils.GoogleOauthFields(**creds_dict)
        return GoogleSheets(auth_creds=auth_creds)

    @cached_property
    def gspread_client(self):
        return self.auth_creds.init_gspread_client()

    def get_spreadsheet_data(self, sheet_id: str):
        google_sheet = self._try_open_spreadsheet(sheet_id=sheet_id)
        return {
            "id": google_sheet.id,
            "title": google_sheet.title,
            "worksheets": [worksheet.title for worksheet in google_sheet.worksheets()],
        }

    def get_worksheet_from_name(self, sheet_id: str, worksheet_name="Sheet1"):
        google_sheet = self._try_open_spreadsheet(sheet_id=sheet_id)
        return google_sheet.worksheet(worksheet_name)

    def get_worksheet_data(self, worksheet: gspread.worksheet.Worksheet):
        return {
            "title": worksheet.title,
            "data": worksheet.get_all_records(),
        }

    def get_worksheet_by_name(self, sheet_id, name):
        return self._try_open_spreadsheet(sheet_id).worksheet(name)

    def _try_open_spreadsheet(self, sheet_id: str):
        try:
            google_sheet = self.gspread_client.open_by_key(sheet_id)
        except gspread.exceptions.APIError as e:
            # can't use get_file_drive_metadata b/c we'd need to add more auth scopes
            # parse the error to find out if it's a non-supported file.
            if (
                e.error["message"]
                == "This operation is not supported for this document"
            ):
                raise InaccessibleDocument("Filetype is unsupported")
            else:
                raise e
        return google_sheet
