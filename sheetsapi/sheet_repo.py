from collections import defaultdict
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Tuple, Union
from datetime import timedelta


import boto3
from boto3.resources.base import ServiceResource
from botocore.exceptions import ClientError
import randomname
import sentry_sdk


from sheetsapi.account_repo import AccountRepo
from sheetsapi.config import Config
from sheetsapi.models.domain_models import RefreshTokenInfo

AccountType = Literal["user", "organization"]
AccountStatus = Literal["free", "premium"]
MemberType = Literal["owner", "member"]


class UserAlreadyExistsError(Exception):
    """Thrown when trying to create a user that already exists"""


class OrganizationNotFoundError(Exception):
    """Thrown if requested org doesn't exist"""


class UserNotFoundError(Exception):
    """Thrown if requested user doesn't exist"""


class SheetNameTakenError(Exception):
    """"""


class SheetApiNotFoundError(Exception):
    """Sheet for key not found"""


class SheetApiRepo:
    def __init__(self, client, table_name: str, account_repo: AccountRepo):
        self.client = client
        self.table_name = table_name
        self.account_repo = account_repo

    @property
    def table(self) -> ServiceResource:
        return self.client.Table(self.table_name)

    @classmethod
    def from_table_name(cls, table_name: str = Config.Constants.SHEETS_API_TABLE):
        client = boto3.resource("dynamodb", region_name=Config.Constants.AWS_REGION)
        account_repo = AccountRepo.from_table_name(
            table_name=Config.Constants.SHEETS_API_TABLE
        )
        return SheetApiRepo(client, table_name, account_repo)

    def create_api(
        self,
        owner_id,
        google_sheet_id: str,
        refresh_token_info: RefreshTokenInfo,
        cache_duration: Optional[int] = 60,  # seconds
    ):
        """Create a new sheet API"""
        if self.account_repo.get_account(owner_id) is None:
            raise UserNotFoundError("User or org does not exist to create sheet API")
        existing_api = self.get_sheet_api_by_google_sheet_id(owner_id, google_sheet_id)
        if existing_api is not None:
            return existing_api

        sheet_api_key = self._create_unique_sheet_pk(owner_id)
        sheet_api_name = sheet_api_key.split("#")[2]

        item = {
            "PK": sheet_api_key,
            "SK": sheet_api_key,
            "sheet_api_name": sheet_api_name,
            "owner_id": owner_id,
            "google_sheet_id": google_sheet_id,
            "refresh_token_info": refresh_token_info.to_dict(),
            "frozen": False,
            "cache_duration": cache_duration,
            "created_at": datetime.now().isoformat(),
            # Add GSI2 attributes for finding sheets by owner
            "GSI2PK": f"ACCOUNT#{owner_id}",
            "GSI2SK": sheet_api_key,
        }

        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK)",
            )
            return item
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise SheetNameTakenError(
                    f"Sheet API with key {sheet_api_key} already exists"
                )
            raise

    def delete_api(self, owner_id: str, sheet_api_name: str):
        """Delete a sheet API and all its analytics records."""
        sheet_api_key = f"SHEET#{owner_id}#{sheet_api_name}"

        deleted_items = defaultdict(int)

        # Check sheet API exists. This will throw if doesn't exist
        self.get_api_metadata(owner_id, sheet_api_name)
        deleted_items["apis"] += 1
        self.table.delete_item(Key={"PK": sheet_api_key, "SK": sheet_api_key})

        # Batch delete all analytics records
        analytics_results = self.table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": f"ANALYTICS#{owner_id}#{sheet_api_name}"},
        )
        analytics_items = analytics_results.get("Item", [])
        deleted_items["analytics_records"] = len(analytics_items)

        if analytics_items:
            for i in range(0, len(analytics_items), 25):
                batch = analytics_items[i : i + 25]
                delete_requests = [
                    {"DeleteRequest": {"Key": {"PK": item["PK"], "SK": item["SK"]}}}
                    for item in batch
                ]

                self.client.meta.client.batch_write_item(
                    RequestItems={self.table_name: delete_requests}
                )

        return dict(deleted_items)

    def get_api_metadata(self, owner_id: str, sheet_api_id: str) -> dict:
        """Get metadata for a specific sheet API"""

        key = f"SHEET#{owner_id}#{sheet_api_id}"
        result = self.table.get_item(Key={"PK": key, "SK": key})
        item = result.get("Item")
        if item is None:
            raise SheetApiNotFoundError(f"Sheet not found with key {key}")

        item["refresh_token_info"] = RefreshTokenInfo(**item["refresh_token_info"])
        return item

    def get_apis_for_account(self, owner_id: str):
        """Get all sheet APIs owned by a specific account (user or organization)."""
        # Check if the owner (user or org) exists
        owner = self.account_repo.get_account(owner_id)
        if not owner:
            raise UserNotFoundError(f"Account with ID {owner_id} not found")

        # Query GSI2 to find all sheets for this owner.
        # Again using a filter is OK since each account will prob
        # have only max ~200 APIs. Revisit this is we really scale.
        response = self.table.query(
            IndexName="GSI2",
            KeyConditionExpression="GSI2PK = :owner_pk",
            FilterExpression="begins_with(PK, :resource_type)",
            ExpressionAttributeValues={
                ":owner_pk": f"ACCOUNT#{owner_id}",
                ":resource_type": f"SHEET#",
            },
        )
        items = response.get("Items", [])
        for item in items:
            item["refresh_token_info"] = RefreshTokenInfo(**item["refresh_token_info"])
        return items

    def get_sheet_api_by_google_sheet_id(self, owner_id, google_sheet_id):
        """Find a sheet API by Google Sheet ID for a specific owner."""
        # lookup all user sheets via GSI2. Filtering is fine/performant
        # b/c users will only have ~1-100 APIs max.
        response = self.table.query(
            IndexName="GSI2",
            KeyConditionExpression="GSI2PK = :owner",
            FilterExpression="google_sheet_id = :sheet_id",
            ExpressionAttributeValues={
                ":owner": f"ACCOUNT#{owner_id}",
                ":sheet_id": google_sheet_id,
            },
        )
        items = response.get("Items", [])
        if not items:
            return None

        item = items[0]
        item["refresh_token_info"] = RefreshTokenInfo(**item["refresh_token_info"])
        return item

    def get_doc_by_google_doc_id(self, owner_id, google_sheet_id):
        """Find a sheet API by Google Sheet ID for a specific owner."""
        # lookup all user sheets via GSI2. Filtering is fine/performant
        # b/c users will only have ~1-100 APIs max.
        response = self.table.query(
            IndexName="GSI2",
            KeyConditionExpression="GSI2PK = :owner",
            FilterExpression="google_doc_id = :sheet_id",
            ExpressionAttributeValues={
                ":owner": f"ACCOUNT#{owner_id}",
                ":sheet_id": google_sheet_id,
            },
        )
        items = response.get("Items", [])
        if not items:
            return None

        item = items[0]
        item["refresh_token_info"] = RefreshTokenInfo(**item["refresh_token_info"])
        return item

    def update_api(
        self,
        owner_id: str,
        sheet_api_name: str,
        fields: dict[str, Any],
    ):
        """Update a sheet API with the provided fields."""
        api_key = f"SHEET#{owner_id}#{sheet_api_name}"

        # Build update expression
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}

        for key, value in fields.items():
            # Skip updating PK and SK
            if key in ["PK", "SK", "GSI2PK", "GSI2SK"]:
                continue

            update_expression_parts.append(f"#{key} = :{key}")
            expression_attribute_values[f":{key}"] = value
            expression_attribute_names[f"#{key}"] = key

        if not update_expression_parts:
            # No valid fields to update
            return self.get_api_metadata(owner_id, sheet_api_name)

        update_expression = "SET " + ", ".join(update_expression_parts)

        try:
            response = self.table.update_item(
                Key={"PK": api_key, "SK": api_key},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
                ConditionExpression="attribute_exists(PK)",
                ReturnValues="ALL_NEW",
            )

            return response.get("Attributes")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise SheetApiNotFoundError(f"Sheet API not found: {api_key}")
            raise

    def unfreeze_apis(self, owner_id: str):
        # Get all sheet APIs for this account
        sheets = self.get_apis_for_account(owner_id)

        # Use batch operations to unfreeze all sheets
        unfrozen_count = 0
        for i in range(0, len(sheets), 25):
            batch = sheets[i : i + 25]
            update_requests = []

            for sheet in batch:
                # Only update if the sheet is currently frozen
                if sheet.get("frozen", False):
                    # Extract the sheet_api_name from the PK
                    # Format is SHEET#owner_id#sheet_api_name
                    parts = sheet["PK"].split("#")
                    if len(parts) >= 3:
                        sheet_api_name = parts[2]
                        try:
                            # For batch operations we need to use PutRequest instead of UpdateRequest
                            # This means we need to get the full item and modify it
                            sheet_item = self.get_api_metadata(
                                owner_id=owner_id, sheet_api_id=sheet_api_name
                            )
                            # Update the frozen status
                            sheet_item["frozen"] = False
                            sheet_item["refresh_token_info"] = sheet_item[
                                "refresh_token_info"
                            ].to_dict()

                            update_requests.append({"PutRequest": {"Item": sheet_item}})
                        except SheetApiNotFoundError as error:
                            sentry_sdk.capture_exception(error)

            if update_requests:  # Only make the API call if there are items to update
                self.client.meta.client.batch_write_item(
                    RequestItems={self.table_name: update_requests}
                )
            unfrozen_count += len(update_requests)
            return unfrozen_count

    def freeze_apis(self, owner_id: str):
        # Get all sheet APIs for this account and sort sheets (newest first)
        sheets = self.get_apis_for_account(owner_id)
        sorted_sheets = sorted(
            sheets, key=lambda item: item.get("created_at", ""), reverse=True
        )
        sheets_to_freeze = sorted_sheets[2:] if len(sorted_sheets) > 2 else []

        # Use batch operations to freeze sheets in batches of 25 (DynamoDB's limit)
        frozen_count = 0
        for i in range(0, len(sheets_to_freeze), 25):
            batch = sheets_to_freeze[i : i + 25]
            update_requests = []

            for sheet in batch:
                # Extract the sheet_api_name from the PK
                # Format is SHEET#owner_id#sheet_api_name
                parts = sheet["PK"].split("#")
                if len(parts) >= 3:
                    sheet_api_name = parts[2]
                    try:
                        # For batch operations we need to use PutRequest instead of UpdateRequest
                        # This means we need to get the full item and modify it
                        sheet_item = self.get_api_metadata(
                            owner_id=owner_id, sheet_api_id=sheet_api_name
                        )
                        # Update the frozen status
                        sheet_item["frozen"] = True
                        sheet_item["refresh_token_info"] = sheet_item[
                            "refresh_token_info"
                        ].to_dict()

                        update_requests.append({"PutRequest": {"Item": sheet_item}})
                    except ValueError as error:
                        sentry_sdk.capture_exception(error)

            self.client.meta.client.batch_write_item(
                RequestItems={self.table_name: update_requests}
            )
            frozen_count += len(update_requests)
        return frozen_count

    def _create_unique_sheet_pk(self, owner_id: str):
        """Create a unique key for a sheet API."""

        def key_exists(key):
            res = self.table.get_item(Key={"PK": key, "SK": key})
            return res.get("Item") is not None

        name = randomname.get_name()
        key = f"SHEET#{owner_id}#{name}"

        while key_exists(key):
            name = randomname.get_name()
            key = f"SHEET#{owner_id}#{name}"
        return key
