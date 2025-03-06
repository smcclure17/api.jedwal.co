import dataclasses
import datetime
import logging

import gspread
import randomname
from sheetsapi import (
    auth_utils,
    dynamodb_sheet_repo,
    google_sheet_client,
    lru_cache,
    user_helpers,
    organization_helpers,
)
from sheetsapi.models.db_models import SheetMetadata

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
        org_id: str | None = None,
    ) -> str:
        """Add a sheet to the repository.

        Args:
            auth_creds: Google OAuth credentials
            sheet_id: ID of the Google Sheet
            email: Email of the user creating the sheet
            org_id: Optional organization ID if creating for an organization

        Returns:
            The API name for the sheet
        """
        user_id = user_helpers.lookup_user_id_by_email(email)

        # Check if the sheet already exists
        if org_id:
            # If org-owned, check org's sheets
            sheets = self.repository.get_sheet_apis_for_org(org_id)
        else:
            # If user-owned, check user's sheets
            sheets = self.repository.get_sheet_apis_for_email(email)

        existing_sheets = [s for s in sheets if s.sheetId == sheet_id]
        if existing_sheets:
            logger.warning("API for Google Sheet already exists, skipping...")
            return existing_sheets[0].apiName

        google_client = google_sheet_client.GoogleSheets(auth_creds=auth_creds)
        api_name = _generate_api_name(self.repository)
        sheet_data = google_client.get_spreadsheet_data(sheet_id=sheet_id)

        # Determine if this is a user-owned or org-owned sheet
        if org_id:
            # Organization-owned sheet
            org = organization_helpers.get_organization(org_id)
            if not org:
                raise ValueError(f"Organization with ID {org_id} not found")

            self.repository.add_sheet(
                dynamodb_sheet_repo.SheetMetadata(
                    PK=f"SHEET#{api_name}",
                    GSI1PK=f"ORG#{org_id}",  # Associate with org instead of user
                    GSI1SK=f"SHEET#{api_name}",
                    sheetId=sheet_id,
                    apiName=api_name,
                    spreadsheetName=sheet_data.title,
                    createdAt=datetime.datetime.now().isoformat(),
                    cdnTtl=60,
                    authCreds=dataclasses.asdict(auth_creds),
                    ownerId=user_id,  # Creator's ID
                    email=email,  # Creator's email
                )
            )
            # No need to increment user's sheet count for org sheets
        else:
            # User-owned sheet
            self.repository.add_sheet(
                dynamodb_sheet_repo.SheetMetadata(
                    PK=f"SHEET#{api_name}",
                    GSI1PK=f"USER#{user_id}",
                    GSI1SK=f"SHEET#{api_name}",
                    sheetId=sheet_id,
                    apiName=api_name,
                    spreadsheetName=sheet_data.title,
                    createdAt=datetime.datetime.now().isoformat(),
                    cdnTtl=60,
                    authCreds=dataclasses.asdict(auth_creds),
                    ownerId=user_id,
                    email=email,
                )
            )
            # Increment user's sheet count for personal sheets
            self.repository.increment_user_sheet_count(email=email)

        return api_name

    def remove_sheet_from_repository(self, name: str, email: str):
        """Delete an API and decrement the user's API count if it's a personal sheet.

        For organization-owned sheets, we just remove the sheet without decrementing
        any user's count.
        """
        # Get the sheet to check if it's user-owned or org-owned
        try:
            sheet = self.repository.get_sheet_api_by_name(name)

            # Check if it's owned by an organization (GSI1PK starts with ORG#)
            is_org_owned = sheet.GSI1PK.startswith("ORG#")

            # Delete the sheet
            self.repository.remove_sheet(name)

            # Only decrement user's count if it's a personal sheet
            if not is_org_owned:
                self.repository.increment_user_sheet_count(email, decrement=True)

        except dynamodb_sheet_repo.SheetNotFound:
            return

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
            sheet.authCreds
        )

        worksheet = cached_worksheet or google_client.get_worksheet_by_name(
            sheet_id=sheet.sheetId, name=worksheet_name
        )
        worksheet_data = google_client.get_worksheet_data(worksheet)

        self.cache.put(key=f"{name}-{worksheet_name}", value=worksheet)

        return {
            "title": worksheet_data.title,
            "data": worksheet_data.data,
            "cdn_ttl": sheet.cdnTtl,
            "frozen": sheet.frozen,
        }

    def get_sheet_api_info(self, name: str):
        return self.repository.get_sheet_api_by_name(name)

    def get_sheet_apis_for_email(
        self, email: str
    ) -> list[dynamodb_sheet_repo.SheetMetadataWithWorksheets]:
        """Get all sheets in the repository that belong to an email address."""
        sheets = self.repository.get_sheet_apis_for_email(email)
        return self._add_worksheets_to_sheets(sheets)

    def get_sheet_apis_for_org(
        self, org_id: str
    ) -> list[dynamodb_sheet_repo.DynamoDBSheetRepository]:
        sheets = self.repository.get_sheet_apis_for_org(org_id)
        return self._add_worksheets_to_sheets(sheets)

    def update_sheet_api_ttl(self, name, ttl):
        self.repository.update_sheet_api_ttl(name, ttl)

    def _add_worksheets_to_sheets(self, sheets: list[SheetMetadata]):
        output: list[dynamodb_sheet_repo.SheetMetadataWithWorksheets] = []
        for sheet in sheets:
            auth_creds = self.repository.get_sheet_auth_credentials(sheet.apiName)
            google_client = google_sheet_client.GoogleSheets(auth_creds=auth_creds)
            worksheets = google_client.get_spreadsheet_data(sheet.sheetId).worksheets
            output.append(
                dynamodb_sheet_repo.SheetMetadataWithWorksheets(
                    **sheet.model_dump(), worksheets=worksheets
                )
            )
        return output


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
