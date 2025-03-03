import dataclasses
import datetime
import logging

import gspread
import randomname
from sheetsapi import auth_utils, dynamodb_sheet_repo, google_sheet_client, lru_cache, user_helpers

logger = logging.getLogger(__name__)


class SheetAlreadyExists(Exception):
    """Raised when a sheet is already in the repository."""


class InaccessibleDocument(Exception):
    "Raised when a Google Sheet cannot be opened, e.g., if it's actually an XLSX"


@dataclasses.dataclass
class SheetManager:
    repository: dynamodb_sheet_repo.DynamoDBSheetRepository = (
        dynamodb_sheet_repo.DynamoDBSheetRepository()
    )
    cache: lru_cache.LRUCache = lru_cache.LRUCache(10)

    def add_sheet_to_repository(
        self,
        auth_creds: auth_utils.GoogleOauthFields,
        sheet_id: str,
        email: str,
        source_org: str | None = None,
    ) -> str:

        sheets = self.repository.get_sheet_apis_for_email(email)
        user_id = user_helpers.lookup_user_by_email(email)["userId"]
        existing_sheet = [s for s in sheets if s["sheet_id"] == sheet_id]
        if existing_sheet:
            logger.warning("API for Google Sheet already exists, skipping...")
            return existing_sheet["api_name"]

        google_client = google_sheet_client.GoogleSheets(auth_creds=auth_creds)
        api_name = _generate_api_name(self.repository)
        sheet_data = google_client.get_spreadsheet_data(sheet_id=sheet_id)
        self.repository.add_sheet(
            sheet_data={
                "id": f"sheet#{api_name}",
                "user_id": user_id,
                "sheet_id": sheet_data["id"],
                "email": email,
                "source_org": source_org or email,
                "spreadsheet_name": sheet_data["title"],
                "api_name": api_name,
                "auth_creds": dataclasses.asdict(auth_creds),
                "cdn_ttl": 15,
                "created_at": datetime.datetime.now().isoformat(),
                "frozen": False,
            },
        )
        self.repository.increment_user_sheet_count(email=email)
        return api_name

    def remove_sheet_from_repository(self, name: str, email: str):
        """Delete an API and decrement the user's API count"""
        self.repository.remove_sheet(name)
        self.repository.increment_user_sheet_count(email, decrement=True)

    def get_worksheet_data(self, name: str, worksheet_name="Sheet1"):
        """Get data from a Google Sheet by name.

        Args:
            name: The name of the sheet in the repository.
            worksheet: The name of the sheet within the Google Sheet.

        Returns:
            The data from the Google Sheet.
        """
        cached_worksheet: gspread.worksheet.Worksheet | None = self.cache.get(
            f"{name}-{worksheet_name}"
        )

        sheet = self.repository.get_sheet_api_by_name(name)
        if sheet is None:
            raise dynamodb_sheet_repo.SheetNotFound(
                f"Sheet with name {name} not found in repository."
            )

        google_client = google_sheet_client.GoogleSheets.from_creds_dict(
            sheet["auth_creds"]
        )

        worksheet = cached_worksheet or google_client.get_worksheet_by_name(
            sheet_id=sheet["sheet_id"], name=worksheet_name
        )
        worksheet_data = google_client.get_worksheet_data(worksheet)

        self.cache.put(key=f"{name}-{worksheet_name}", value=worksheet)

        return {
            "title": worksheet_data["title"],
            "data": worksheet_data["data"],
            "cdn_ttl": sheet.get("cdn_ttl", 15),
            "frozen": sheet.get("frozen"),
        }

    def get_sheet_api_info(self, name: str):
        return self.repository.get_sheet_api_by_name(name)

    def get_sheet_apis_for_email(self, email: str):
        """Get all sheets in the repository that belong to an email address."""

        sheets = self.repository.get_sheet_apis_for_email(email)
        output = []
        for sheet in sheets:
            auth_creds = self.repository.get_sheet_auth_credentials(sheet["api_name"])
            google_client = google_sheet_client.GoogleSheets(auth_creds=auth_creds)
            worksheets = google_client.get_spreadsheet_data(sheet["sheet_id"])[
                "worksheets"
            ]
            output.append({**sheet, "worksheets": worksheets})
        return output

    def update_sheet_api_ttl(self, name, ttl):
        self.repository.update_sheet_api_ttl(name, ttl)


def _generate_api_name(repo: dynamodb_sheet_repo.DynamoDBSheetRepository) -> str:
    """Generate a random unique name that does not already exist in the repository.

    Args:
        repo: The repository to check for name conflicts.

    Returns:
        A unique name.
    """
    name = randomname.get_name()
    while repo.sheet_api_exists(name):
        name = randomname.get_name()
    return name
