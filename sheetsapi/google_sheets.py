import dataclasses
from typing import Optional
import randomname
import gspread

from sheetsapi import dynamodb_client, lru_cache
from sheetsapi.auth_utils import GoogleOauthFields
from sheetsapi.config import Config


class SheetNotFound(Exception):
    """Raised when a sheet is not found in the repository."""


class SheetAlreadyExists(Exception):
    """Raised when a sheet is already in the repository."""


class InvalidCredentials(Exception):
    """Raised when credentials are invalid."""


@dataclasses.dataclass
class GoogleSheets:
    repository: dynamodb_client.DynamoDBClient = dataclasses.field(
        default_factory=dynamodb_client.DynamoDBClient
    )
    hot_worksheet_cache: lru_cache.LRUCache = dataclasses.field(
        default_factory=lambda: lru_cache.LRUCache(10)
    )

    def add_sheet_to_repository(
        self,
        auth_creds: GoogleOauthFields,
        sheet_id: str,
        email: str,
    ) -> str:
        """Add a Google Sheet to the repository.

        Args:
            sheet_id: The ID of the Google Sheet.
            sheet_name: The name of the sheet within the Google Sheet.
            name: The name to use for the sheet in the repository.

        Returns:
            The name used for the sheet in the repository."""
        if self.repository.query_index(
            Config.Constants.SHEETS_API_TABLE, "sheet_id-index", "sheet_id", sheet_id
        ):
            raise SheetAlreadyExists(f"Sheet with ID {sheet_id} already in repository.")

        name = _generate_api_name(self.repository)
        user_client = auth_creds.init_gspread_client()
        sheet = user_client.open_by_key(sheet_id)
        self.repository.put_item(
            Config.Constants.SHEETS_API_TABLE,
            {
                "id": f"sheet-{name}",
                "sheet_id": sheet.id,
                "email": email,
                "spreadsheet_name": sheet.title,
                "api_name": name,
                "auth_creds": dataclasses.asdict(auth_creds),
                "cdn_ttl": 15,
            },
        )
        return name

    def get_sheet_data(self, name: str, worksheet_name: str = "Sheet1"):
        """Get data from a Google Sheet by name.

        Args:
            name: The name of the sheet in the repository.
            worksheet: The name of the sheet within the Google Sheet.

        Returns:
            The data from the Google Sheet.
        """
        worksheet: gspread.worksheet.Worksheet | None = self.hot_worksheet_cache.get(
            f"{name}-{worksheet_name}"
        )
        if worksheet is not None:
            return {
                "title": worksheet.title,
                "data": worksheet.get_all_records(),
                "cdn_ttl": 15,  # todo: save this in the repository
            }  # TODO: make this a dataclass/pydantic model instead

        sheet = self.repository.get_item(
            Config.Constants.SHEETS_API_TABLE, {"id": f"sheet-{name}"}
        )
        if sheet is None:
            raise SheetNotFound(f"Sheet with name {name} not found in repository.")
        auth_creds = GoogleOauthFields(**sheet["auth_creds"])

        client = auth_creds.init_gspread_client()
        google_sheet = client.open_by_key(sheet["sheet_id"])
        worksheet = google_sheet.worksheet(worksheet_name)
        self.hot_worksheet_cache.put(f"{name}-{worksheet_name}", worksheet)
        return {
            "title": worksheet.title,
            "data": worksheet.get_all_records(),
            "cdn_ttl": sheet.get("cdn_ttl", 15),
        }  # TODO: make this a dataclass/pydantic model instead

    def get_sheet_name_from_id(self, sheet_id: str) -> Optional[str]:
        """Get the name of a sheet in the repository by Google Sheet ID."""
        sheets = self.repository.query_index(
            Config.Constants.SHEETS_API_TABLE, "sheet_id-index", "sheet_id", sheet_id
        )
        assert len(sheets) <= 1, f"Multiple sheets with ID {sheet_id} found."
        return sheets[0]["api_name"] if sheets else None

    def get_sheets_for_email(self, email: str) -> list[dict]:
        """Get all sheets in the repository that belong to an email address."""
        sheets = self.repository.query_index(
            Config.Constants.SHEETS_API_TABLE, "email-index", "email", email
        )
        return [
            {
                "api_name": sheet["api_name"],
                "spreadsheet_name": sheet["spreadsheet_name"],
                "sheet_id": sheet["sheet_id"],
            }
            for sheet in sheets
            if sheet["id"].startswith("sheet-")  # HACK, do better single-table design
        ]

    def get_sheet_worksheets(self, name: str) -> list[str]:
        """Get the worksheets for a sheet in the repository.

        Args:
            name: The name of the sheet in the repository.

        Returns:
            The names of the worksheets in the Google Sheet."""
        sheet = self.repository.get_item(
            Config.Constants.SHEETS_API_TABLE, {"id": f"sheet-{name}"}
        )
        if sheet is None:
            raise SheetNotFound(f"Sheet with name {name} not found in repository.")

        auth_creds = GoogleOauthFields(**sheet["auth_creds"])
        client = auth_creds.init_gspread_client()
        sheet = client.open_by_key(sheet["sheet_id"])
        return [worksheet.title for worksheet in sheet.worksheets()]

    def get_sheet_info(self, name: str) -> tuple[dict, list[str]]:
        """Get the API from storage by name, and also return all the worksheets available"""

        sheet = self.repository.get_item(
            Config.Constants.SHEETS_API_TABLE, {"id": f"sheet-{name}"}
        )
        if sheet is None:
            raise SheetNotFound(f"Sheet with name {name} not found in repository.")

        auth_creds = GoogleOauthFields(**sheet["auth_creds"])
        client = auth_creds.init_gspread_client()
        spreadsheet = client.open_by_key(sheet["sheet_id"])
        worksheets = [worksheet.title for worksheet in spreadsheet.worksheets()]
        return sheet, worksheets


def _generate_api_name(repo: dynamodb_client.DynamoDBClient) -> str:
    """Generate a random unique name that does not already exist in the repository.

    Args:
        repo: The repository to check for name conflicts.

    Returns:
        A unique name.
    """
    name = randomname.get_name()
    while repo.get_item(Config.Constants.SHEETS_API_TABLE, {"id": f"sheet-{name}"}):
        name = randomname.get_name()
    return name
