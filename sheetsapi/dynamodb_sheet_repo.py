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

    def remove_sheet(self, sheet_uuid: str):
        """Remove a sheet by its UUID"""
        key = {"PK": f"SHEET#{sheet_uuid}", "SK": "#METADATA"}
        self.repository.delete_item(Config.Constants.SHEETS_API_TABLE, key=key)
    
    def remove_sheet_by_api_name(self, api_name: str):
        """Remove a sheet by its API name"""
        sheet = self.get_sheet_api_by_name(api_name)
        if sheet:
            self.remove_sheet(sheet.uuid)

    def get_sheet_api_by_uuid(self, sheet_uuid: str) -> SheetMetadata:
        """Retrieve a sheet by its UUID"""
        sheet = self.repository.get_item(
            Config.Constants.SHEETS_API_TABLE,
            {"PK": f"SHEET#{sheet_uuid}", "SK": "#METADATA"},
        )
        if sheet is None:
            raise SheetNotFound(f"Sheet with UUID {sheet_uuid} not found in repository.")
        return SheetMetadata(**sheet)

    def get_sheet_api_by_name(self, api_name: str) -> SheetMetadata:
        """Retrieve a sheet by its API name using GSI2"""
        sheets = self.repository.query_index(
            Config.Constants.SHEETS_API_TABLE,
            "GSI2",
            "GSI2PK",
            "API",
            KeyConditionExpression="GSI2PK = :pk AND GSI2SK = :sk",
            ExpressionAttributeValues={":pk": "API", ":sk": f"API#{api_name}"},
        )
        
        if not sheets or len(sheets) == 0:
            raise SheetNotFound(f"Sheet with API name {api_name} not found in repository.")
        
        # Should only be one sheet with this API name
        return SheetMetadata(**sheets[0])

    def sheet_api_exists(self, api_name: str) -> bool:
        """Check if an API name is already in use"""
        try:
            self.get_sheet_api_by_name(api_name)
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

    def get_sheet_auth_credentials(self, api_name):
        """Get the auth credentials for a sheet by API name"""
        creds = self.get_sheet_api_by_name(api_name).authCreds
        return auth_utils.GoogleOauthFields(**creds)
        
    def get_sheet_auth_credentials_by_uuid(self, uuid):
        """Get the auth credentials for a sheet by UUID"""
        creds = self.get_sheet_api_by_uuid(uuid).authCreds
        return auth_utils.GoogleOauthFields(**creds)

    def update_sheet_api_ttl(self, api_name, ttl):
        # First get the sheet by API name to get the UUID
        sheet = self.get_sheet_api_by_name(api_name)
        
        # Then update using the UUID as the primary key
        self.repository.update_item(
            table=Config.Constants.SHEETS_API_TABLE,
            key={"PK": f"SHEET#{sheet.uuid}", "SK": "#METADATA"},
            item={"cdnTtl": ttl},
        )
