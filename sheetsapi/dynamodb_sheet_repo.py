import dataclasses
from sheetsapi import auth_utils, dynamodb_client, user_helpers
from sheetsapi.config import Config


class SheetNotFound(Exception):
    """Raised when a sheet is not found in the repository."""


@dataclasses.dataclass(frozen=True)
class DynamoDBSheetRepository:
    repository: dynamodb_client.DynamoDBClient = dataclasses.field(
        default_factory=dynamodb_client.DynamoDBClient
    )

    def add_sheet(self, sheet_data: dict):
        """Add a sheet and its metadata"""
        # Transform to new schema
        sheet_name = sheet_data["api_name"]
        owner_id = sheet_data["user_id"]  # Assuming this is passed in

        transformed_data = {
            "PK": f"SHEET#{sheet_name}",
            "SK": "#METADATA",
            "GSI1PK": f"USER#{owner_id}",
            "GSI1SK": f"SHEET#{sheet_name}",
            "sheetId": sheet_data["sheet_id"],
            "apiName": sheet_data["api_name"],
            "spreadsheetName": sheet_data["spreadsheet_name"],
            "createdAt": sheet_data["created_at"],
            "cdnTtl": sheet_data["cdn_ttl"],
            "frozen": sheet_data.get("frozen", False),
            "authCreds": sheet_data["auth_creds"],
            "ownerId": owner_id,
            "email": sheet_data["email"],  # Keep for backwards compatibility
            "sourceOrg": sheet_data.get("source_org"),
        }

        self.repository.put_item(
            Config.Constants.SHEETS_API_TABLE,
            item=transformed_data,
        )

    def remove_sheet(self, name: str):
        key = {"PK": f"SHEET#{name}", "SK": "#METADATA"}
        self.repository.delete_item(Config.Constants.SHEETS_API_TABLE, key=key)

    def get_sheet_api_by_name(self, name: str):
        """Retrieve a sheet"""
        sheet = self.repository.get_item(
            Config.Constants.SHEETS_API_TABLE,
            {"PK": f"SHEET#{name}", "SK": "#METADATA"},
        )
        if sheet is None:
            raise SheetNotFound(f"Sheet with name {name} not found in repository.")

        # Transform to old format for backwards compatibility
        return {
            "id": f"sheet#{sheet['apiName']}",
            "api_name": sheet["apiName"],
            "spreadsheet_name": sheet["spreadsheetName"],
            "created_at": sheet["createdAt"],
            "sheet_id": sheet["sheetId"],
            "cdn_ttl": sheet["cdnTtl"],
            "frozen": sheet.get("frozen"),
            "auth_creds": sheet["authCreds"],
            "email": sheet["email"],
            "source_org": sheet.get("sourceOrg") or sheet["email"],
        }

    def sheet_api_exists(self, name: str):
        try:
            self.get_sheet_api_by_name(name)
            return True
        except SheetNotFound:
            return False

    def get_sheet_apis_for_email(self, email: str):
        """Get all sheets for a given email"""
        try:
            user_id = user_helpers.lookup_user_by_email(email)["userId"]
        except user_helpers.UserNotFound:
            return []

        # Then get all sheets for that user using GSI1
        sheets = self.repository.query_index(
            Config.Constants.SHEETS_API_TABLE,
            "GSI1",
            "GSI1PK",
            f"USER#{user_id}",
            KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :sk)",
            ExpressionAttributeValues={":sk": "SHEET#"},
        )

        output_sheets = []
        for sheet in sheets:
            output = {
                "id": f"sheet#{sheet['apiName']}",
                "created_at": sheet["createdAt"],
                "api_name": sheet["apiName"],
                "spreadsheet_name": sheet["spreadsheetName"],
                "sheet_id": sheet["sheetId"],
                "source_org": sheet.get("sourceOrg") or sheet["email"],
                "cdn_ttl": sheet["cdnTtl"],
                "frozen": sheet.get("frozen"),
            }
            output_sheets.append(output)
        return output_sheets

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
        creds = self.get_sheet_api_by_name(name)["auth_creds"]
        return auth_utils.GoogleOauthFields(**creds)

    def update_sheet_api_ttl(self, name, ttl):
        self.repository.update_item(
            table=Config.Constants.SHEETS_API_TABLE,
            key={"PK": f"SHEET#{name}", "SK": "#METADATA"},
            item={"cdnTtl": ttl},
        )
