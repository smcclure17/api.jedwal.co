import dataclasses
from sheetsapi import auth_utils, dynamodb_client, user_helpers
from sheetsapi.config import Config
from sheetsapi.models.db_models import SheetMetadata


class SheetNotFound(Exception):
    """Raised when a sheet is not found in the repository."""


@dataclasses.dataclass(frozen=True)
class DynamoDBSheetRepository:
    repository: dynamodb_client.DynamoDBClient = dataclasses.field(
        default_factory=dynamodb_client.DynamoDBClient
    )

    def add_sheet(self, sheet_data: SheetMetadata):
        """Add a sheet and its metadata"""
        self.repository.put_item(
            Config.Constants.SHEETS_API_TABLE,
            item=sheet_data.model_dump(),
        )

    def remove_sheet(self, name: str):
        key = {"PK": f"SHEET#{name}", "SK": "#METADATA"}
        self.repository.delete_item(Config.Constants.SHEETS_API_TABLE, key=key)

    def get_sheet_api_by_name(self, name: str) -> SheetMetadata:
        """Retrieve a sheet"""
        sheet = self.repository.get_item(
            Config.Constants.SHEETS_API_TABLE,
            {"PK": f"SHEET#{name}", "SK": "#METADATA"},
        )
        if sheet is None:
            raise SheetNotFound(f"Sheet with name {name} not found in repository.")
        return SheetMetadata(**sheet)

    def sheet_api_exists(self, name: str) -> bool:
        try:
            self.get_sheet_api_by_name(name)
            return True
        except SheetNotFound:
            return False

    def get_sheet_apis_for_email(self, email: str) -> list[SheetMetadata]:
        """Get all sheets for a given email (only personal sheets, not org sheets)"""
        try:
            user_id = user_helpers.lookup_user_id_by_email(email)
        except user_helpers.UserNotFound:
            return []

        # Get all sheets for that user using GSI1
        sheets = self.repository.query_index(
            Config.Constants.SHEETS_API_TABLE,
            "GSI1",
            "GSI1PK",
            f"USER#{user_id}",
            KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :sk)",
            ExpressionAttributeValues={":sk": "SHEET#"},
        )
        return [SheetMetadata(**sheet) for sheet in sheets]

    def get_sheet_apis_for_org(self, org_id: str) -> list[SheetMetadata]:
        """Get all sheets for a given organization"""
        # Get all sheets for that organization using GSI1
        sheets = self.repository.query_index(
            Config.Constants.SHEETS_API_TABLE,
            "GSI1",
            "GSI1PK",
            f"ORG#{org_id}",
            KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :sk)",
            ExpressionAttributeValues={":sk": "SHEET#"},
        )
        return [SheetMetadata(**sheet) for sheet in sheets]

    def increment_user_sheet_count(self, email: str, decrement=False):
        """Update user sheet count"""
        # First get user ID from email
        user_lookup = self.repository.get_item(
            Config.Constants.SHEETS_API_TABLE, {"PK": f"EMAIL#{email}", "SK": "#LOOKUP"}
        )

        if not user_lookup:
            raise ValueError(f"User with email {email} not found")

        user_id = user_lookup["userId"]

        self.repository.increment_item_field(
            Config.Constants.SHEETS_API_TABLE,
            key={"PK": f"USER#{user_id}", "SK": "#PROFILE"},
            field="apiCount",
            decrement=decrement,
        )

    def get_sheet_auth_credentials(self, name):
        creds = self.get_sheet_api_by_name(name).authCreds
        return auth_utils.GoogleOauthFields(**creds)

    def update_sheet_api_ttl(self, name, ttl):
        self.repository.update_item(
            table=Config.Constants.SHEETS_API_TABLE,
            key={"PK": f"SHEET#{name}", "SK": "#METADATA"},
            item={"cdnTtl": ttl},
        )
