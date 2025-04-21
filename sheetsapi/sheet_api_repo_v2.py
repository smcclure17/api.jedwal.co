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


from sheetsapi.config import Config
from sheetsapi.models.domain_models import RefreshTokenInfo
from sheetsapi.models.db_models import RateLimitRecord

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


class RateLimitExceededError(Exception):
    """Rate limit exceeded"""

    def __init__(
        self, resource_type: str, resource_id: str, limit: int, reset_time: str
    ):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.limit = limit
        self.reset_time = reset_time
        super().__init__(
            f"Rate limit exceeded for {resource_type}:{resource_id}. "
            f"Limit: {limit}, resets at {reset_time}"
        )


class SheetApiRepo:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name

    @property
    def table(self) -> ServiceResource:
        return self.client.Table(self.table_name)

    @classmethod
    def from_table_name(cls, table_name: str = Config.Constants.SHEETS_API_TABLE):
        client = boto3.resource("dynamodb", region_name=Config.Constants.AWS_REGION)
        return SheetApiRepo(client, table_name)

    def check_rate_limit(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 167,  # 167 * 30 = ~5k monthly requests 
        window_seconds: int = 86400, # one day
    ) -> Tuple[bool, int]:
        """Check if a resource has exceeded its rate limit

        Args:
            resource_type: Type of resource (IP, API, USER, etc.)
            resource_id: ID of the resource (IP address, API ID, user ID)
            limit: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds (default: 60 seconds = 1 minute)

        Returns:
            Tuple[bool, int]: (has_exceeded_limit, current_count)

        Raises:
            RateLimitExceededError: If rate limit is exceeded
        """
        now = datetime.now(timezone.utc)
        # Create a timestamp rounded to the minute: YYYY-MM-DD
        timestamp_day = now.strftime("%Y-%m-%d")

        # Format for finding our rate limit record
        pk = f"RATE#{resource_type}#{resource_id}"
        sk = timestamp_day

        try:
            # Try to update an existing count, or create if not exists
            response = self.table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression="ADD #count :increment SET expiresAt = :expires_at",
                ExpressionAttributeNames={"#count": "count"},
                ExpressionAttributeValues={
                    ":increment": 1,
                    ":expires_at": int(time.time()) + window_seconds + 300,  # Add buffer
                },
                ReturnValues="UPDATED_NEW",
            )

            # Get the updated count
            current_count = response.get("Attributes", {}).get("count", 1)

            # Check if over limit
            if current_count > limit:
                # Calculate when the rate limit resets
                reset_time = (
                    now.replace(second=0, microsecond=0) + timedelta(minutes=1)
                ).isoformat()
                raise RateLimitExceededError(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    limit=limit,
                    reset_time=reset_time,
                )

            return False, current_count

        except Exception as e:
            # Handle other errors (like throttling, connection issues, etc.)
            if not isinstance(e, RateLimitExceededError):
                sentry_sdk.capture_exception(e)
                # If we fail, default to allowing the request
                return False, 0
            else:
                raise

    def get_rate_limit_counts(
        self, resource_type: str, resource_id: str, minutes: int = 5
    ) -> Dict[str, int]:
        """Get rate limit counts for a resource over multiple minutes

        Args:
            resource_type: Type of resource (IP, API, USER, etc.)
            resource_id: ID of the resource (IP address, API ID, user ID)
            minutes: Number of minutes to retrieve (default: 5)

        Returns:
            Dict[str, int]: Dictionary mapping minute timestamps to request counts
        """
        now = datetime.now(timezone.utc)
        counts = {}

        # Query for the last 'minutes' worth of rate limit records
        try:
            response = self.table.query(
                KeyConditionExpression="#pk = :pk AND #sk > :min_time",
                ExpressionAttributeNames={"#pk": "PK", "#sk": "SK"},
                ExpressionAttributeValues={
                    ":pk": f"RATE#{resource_type}#{resource_id}",
                    ":min_time": (now - timedelta(minutes=minutes)).strftime(
                        "%Y-%m-%dT%H:%M"
                    ),
                },
            )

            items = response.get("Items", [])
            for item in items:
                counts[item["SK"]] = item.get("count", 0)

            return counts

        except Exception as e:
            sentry_sdk.capture_exception(e)
            return {}

    def create_user(
        self,
        user_id: str,  # Google SUB id
        email: str,
        refresh_token_info: RefreshTokenInfo,
        given_name: str,
        family_name: str,
        account_status: Optional[AccountStatus] = "free",
    ):
        """Create a new user. Fails if user already exists."""
        item = {
            "PK": f"ACCOUNT#{user_id}",
            "SK": f"ACCOUNT#{user_id}",
            "type": "user",
            "account_id": user_id,
            "display_name": f"{given_name} {family_name}",
            "email": email,
            "refresh_token_info": refresh_token_info.to_dict(),
            "given_name": given_name,
            "family_name": family_name,
            "account_status": account_status,
            "created_at": datetime.now().isoformat(),
            # GSI for looking up users by email
            "GSI3PK": f"EMAIL#{email.lower()}",  # Use lowercase for case-insensitive lookups
            "GSI3SK": f"ACCOUNT#{user_id}",
        }

        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK)",
            )
            return item
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise UserAlreadyExistsError(
                    f"User or Org with ID {user_id} already exists"
                )
            raise

    def delete_user(self, user_id: str):
        """
        Delete a user and all associated data atomically using transactions.
        This includes:
        - The user account item
        - All sheet APIs owned by the user
        - All organization memberships for the user

        TODO: need to clean up orgs owned by this user somehow
        to avoid orphaned orgs.

        Args:
            user_id: The ID of the user to delete

        Returns:
            A summary of what was deleted

        Raises:
            UserNotFoundError: If the user doesn't exist
        """
        # Check if user exists
        self._check_user_exists(user_id)

        deleted_items = defaultdict(int)

        # Collect all items that need to be deleted
        items_to_delete = []

        # 1. Get all sheets owned by the user via GSI2
        sheets_response = self.table.query(
            IndexName="GSI2",
            KeyConditionExpression="GSI2PK = :owner",
            ExpressionAttributeValues={":owner": f"ACCOUNT#{user_id}"},
        )

        for sheet in sheets_response.get("Items", []):
            items_to_delete.append(
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": {"PK": sheet["PK"], "SK": sheet["SK"]},
                    }
                }
            )
            deleted_items["sheets"] += 1

        # 2. Get all organization memberships for the user via GSI1
        memberships_response = self.table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :membership",
            ExpressionAttributeValues={":membership": f"MEMBERSHIP#{user_id}"},
        )

        for membership in memberships_response.get("Items", []):
            items_to_delete.append(
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": {"PK": membership["PK"], "SK": membership["SK"]},
                    }
                }
            )
            deleted_items["memberships"] += 1

        # 3. Add the user account item to delete
        items_to_delete.append(
            {
                "Delete": {
                    "TableName": self.table_name,
                    "Key": {"PK": f"ACCOUNT#{user_id}", "SK": f"ACCOUNT#{user_id}"},
                }
            }
        )
        deleted_items["user"] = 1

        # Execute transactions in batches of 25 (DynamoDB's limit)
        for i in range(0, len(items_to_delete), 25):
            batch = items_to_delete[i : i + 25]
            self.client.meta.client.transact_write_items(TransactItems=batch)

        return dict(deleted_items)

    def delete_organization(self, org_id: str):
        self._check_org_exists(org_id=org_id)
        deleted_items = defaultdict(int)
        items_to_delete = []

        # Delete sheets
        sheet_apis = self.get_sheet_apis_for_account(org_id)
        for sheet_api in sheet_apis:
            items_to_delete.append(
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": {"PK": sheet_api["PK"], "SK": sheet_api["SK"]},
                    }
                }
            )
            deleted_items["sheets"] += 1

        # Delete membership records
        members = self.get_users_for_org(org_id)
        for member in members:
            items_to_delete.append(
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": {"PK": member["PK"], "SK": member["SK"]},
                    }
                }
            )

        # Delete the org itself
        items_to_delete.append(
            {
                "Delete": {
                    "TableName": self.table_name,
                    "Key": {"PK": f"ACCOUNT#{org_id}", "SK": f"ACCOUNT#{org_id}"},
                }
            }
        )
        deleted_items["organization"] = 1  # Count the org itself

        for i in range(0, len(items_to_delete), 25):
            batch = items_to_delete[i : i + 25]
            self.client.meta.client.transact_write_items(TransactItems=batch)

        return dict(deleted_items)

    def create_organization(
        self,
        org_name: str,
        created_by: str,  # owner user_id,
        members: Optional[list[str]] = None,  # user_ids of members
    ):
        """Create an organization with it's members."""
        if members is None:
            members = []

        org_id = re.sub(r"\s+", "-", org_name).lower()  # My Org --> my-org
        org_item = {
            "PK": f"ACCOUNT#{org_id}",
            "SK": f"ACCOUNT#{org_id}",
            "type": "organization",
            "account_id": org_id,
            "display_name": org_name,
            "account_status": "premium",
            "created_at": datetime.now().isoformat(),
            "created_by": created_by,
            "billing_account_id": created_by,
        }

        # Prepare transaction items
        transaction_items = [
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": org_item,
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        ]

        # Add membership items to the transaction
        users_to_add = [(created_by, "owner")] + [(user, "member") for user in members]
        for user_id, member_type in users_to_add:
            membership_item = {
                "PK": f"ACCOUNT#{org_id}",
                "SK": f"MEMBERSHIP#{user_id}",
                "user_id": user_id,
                "org_id": org_id,
                "member_type": member_type,
                "joined_at": datetime.now().isoformat(),
                # Add GSI1 attributes for reverse lookup (user → orgs)
                "GSI1PK": f"MEMBERSHIP#{user_id}",
                "GSI1SK": f"ACCOUNT#{org_id}",
            }

            transaction_items.append(
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": membership_item,
                    }
                }
            )

        try:
            self.client.meta.client.transact_write_items(
                TransactItems=transaction_items
            )
            return {
                "account_id": org_id,
                "members_added": len(users_to_add),
                "created_at": org_item["created_at"],
                "created_by": org_item["created_by"],
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "TransactionCanceledException":
                raise UserAlreadyExistsError(
                    f"Organization or user with ID {org_id} already exists"
                )
            raise

    def get_account(self, id: str) -> dict | None:
        """Get a user or organization by ID."""
        response = self.table.get_item(
            Key={"PK": f"ACCOUNT#{id}", "SK": f"ACCOUNT#{id}"}
        )
        account = response.get("Item", None)
        if account is None:
            return None
        if account["type"] == "user":
            account["refresh_token_info"] = RefreshTokenInfo(
                **account["refresh_token_info"]
            )
        return account

    def get_accounts(self, ids: list[str]) -> list[dict]:
        """Retrieve accounts from a list of account IDs.

        Args:
            ids: A list of account IDs to retrieve

        Returns:
            A list of account dictionaries for the found accounts
        """
        # Handle empty list case
        if not ids:
            return []

        # Use BatchGetItem for efficient retrieval of multiple items
        request_items = {
            self.table.name: {
                "Keys": [{"PK": f"ACCOUNT#{id}", "SK": f"ACCOUNT#{id}"} for id in ids]
            }
        }

        response = self.table.meta.client.batch_get_item(RequestItems=request_items)

        # Extract the items from the response
        items = response.get("Responses", {}).get(self.table.name, [])

        # Handle pagination if all items weren't returned in one request
        unprocessed_keys = response.get("UnprocessedKeys", {})
        while unprocessed_keys and unprocessed_keys.get(self.table.name):
            response = self.table.meta.client.batch_get_item(
                RequestItems=unprocessed_keys
            )
            items.extend(response.get("Responses", {}).get(self.table.name, []))
            unprocessed_keys = response.get("UnprocessedKeys", {})

        for item in items:
            if item["type"] == "user":
                item["refresh_token_info"] = RefreshTokenInfo(
                    **item["refresh_token_info"]
                )
        return items

    def get_users_for_org(self, org_id: str):
        """Get all user memberships for an organization."""
        self._check_org_exists(org_id)

        # Query all memberships for this organization
        response = self.table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"ACCOUNT#{org_id}",
                ":sk_prefix": "MEMBERSHIP#",
            },
        )
        return response.get("Items", [])

    def get_org_memberships_for_user(self, user_id: str):
        """Get all organization memberships that a user is a member of."""
        self._check_user_exists(user_id)

        # Query GSI1 to find all organizations the user is a member of
        response = self.table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :gsi1pk",
            ExpressionAttributeValues={":gsi1pk": f"MEMBERSHIP#{user_id}"},
        )
        return response.get("Items", [])

    # TODO: Make this a batch process, but that's not a big deal
    def add_user_to_org(
        self, user_id: str, org_id: str, member_type: Optional[MemberType] = "member"
    ):
        self._check_org_exists(org_id)
        self._check_user_exists(user_id)
        membership_item = {
            "PK": f"ACCOUNT#{org_id}",
            "SK": f"MEMBERSHIP#{user_id}",
            "user_id": user_id,
            "org_id": org_id,
            "member_type": member_type,
            "joined_at": datetime.now().isoformat(),
            # Add GSI1 attributes for reverse lookup (user → orgs)
            "GSI1PK": f"MEMBERSHIP#{user_id}",
            "GSI1SK": f"ACCOUNT#{org_id}",
        }
        self.table.put_item(Item=membership_item)

    def create_sheet_api(
        self,
        owner_id,
        google_sheet_id: str,
        refresh_token_info: RefreshTokenInfo,
        cache_duration: Optional[int] = 60,  # seconds
    ):
        """Create a new sheet API"""
        if self.get_account(owner_id) is None:
            raise UserNotFoundError("User or org does not exist to create sheet API")
        existing_api = self.get_sheet_api_by_google_sheet_id(owner_id, google_sheet_id)
        if existing_api is not None:
            return existing_api

        sheet_api_key = self._create_unique_sheet_api_key(owner_id)
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

    def delete_sheet_api(self, owner_id: str, sheet_api_name: str):
        """Delete a sheet API and all its analytics records."""
        sheet_api_key = f"SHEET#{owner_id}#{sheet_api_name}"

        deleted_items = defaultdict(int)

        # Check sheet API exists. This will throw if doesn't exist
        self.get_sheet_api_metadata(owner_id, sheet_api_name)
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

    def check_user_access_for_owner(self, user_id: str, owner_id: str):
        """Check if a user has access to sheets of an owner (user or org)"""
        if user_id == owner_id:
            return True  # User directly owns the sheet

        # Check if owner is an organization
        owner = self.get_account(owner_id)
        if not owner or owner.get("type") != "organization":
            return False

        # Check if user is a member of the organization
        membership = self.table.get_item(
            Key={"PK": f"ACCOUNT#{owner_id}", "SK": f"MEMBERSHIP#{user_id}"}
        ).get("Item")
        return membership is not None

    def get_sheet_api_metadata(self, owner_id: str, sheet_api_id: str) -> dict:
        """Get metadata for a specific sheet API"""
        key = f"SHEET#{owner_id}#{sheet_api_id}"
        result = self.table.get_item(Key={"PK": key, "SK": key})
        item = result.get("Item")
        if item is None:
            raise SheetApiNotFoundError(f"Sheet not found with key {key}")

        item["refresh_token_info"] = RefreshTokenInfo(**item["refresh_token_info"])
        return item

    def get_sheet_apis_for_account(self, owner_id: str):
        """Get all sheet APIs owned by a specific account (user or organization)."""
        # Check if the owner (user or org) exists
        owner = self.get_account(owner_id)
        if not owner:
            raise UserNotFoundError(f"Account with ID {owner_id} not found")

        # Query GSI2 to find all sheets for this owner
        response = self.table.query(
            IndexName="GSI2",
            KeyConditionExpression="GSI2PK = :owner_pk",
            ExpressionAttributeValues={":owner_pk": f"ACCOUNT#{owner_id}"},
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

    def update_sheet_api(
        self, owner_id: str, sheet_api_name: str, fields: dict[str, Any]
    ):
        """Update a sheet API with the provided fields."""
        sheet_api_key = f"SHEET#{owner_id}#{sheet_api_name}"

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
            return self.get_sheet_api_metadata(owner_id, sheet_api_name)

        update_expression = "SET " + ", ".join(update_expression_parts)

        try:
            response = self.table.update_item(
                Key={"PK": sheet_api_key, "SK": sheet_api_key},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
                ConditionExpression="attribute_exists(PK)",
                ReturnValues="ALL_NEW",
            )

            return response.get("Attributes")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise SheetApiNotFoundError(f"Sheet API not found: {sheet_api_key}")
            raise

    def update_account(self, account_id: str, fields: dict[str, Any]):
        """Update a sheet API with the provided fields."""
        account_key = f"ACCOUNT#{account_id}"

        # Build update expression
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}

        for key, value in fields.items():
            # Skip updating PK and SK
            if key in ["PK", "SK", "GSI2PK", "GSI2SK", "GSI3PK", "GSI3SK"]:
                continue

            update_expression_parts.append(f"#{key} = :{key}")
            expression_attribute_values[f":{key}"] = value
            expression_attribute_names[f"#{key}"] = key

        if not update_expression_parts:
            return None

        update_expression = "SET " + ", ".join(update_expression_parts)

        try:
            response = self.table.update_item(
                Key={"PK": account_key, "SK": account_key},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
                ConditionExpression="attribute_exists(PK)",
                ReturnValues="ALL_NEW",
            )

            return response.get("Attributes")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise SheetApiNotFoundError(f"Account not found: {account_key}")
            raise

    def get_user_by_email(self, email: str) -> dict | None:
        """Find a user by their email address.

        Not for organizations, which have no emails
        """
        response = self.table.query(
            IndexName="GSI3",
            KeyConditionExpression="GSI3PK = :email_pk",
            ExpressionAttributeValues={":email_pk": f"EMAIL#{email.lower()}"},
        )

        items = response.get("Items", [])
        if not items:
            raise UserNotFoundError(f"User with email {email} not found.")
        item = items[0]
        item["refresh_token_info"] = RefreshTokenInfo(**item["refresh_token_info"])
        return item

    def downgrade_account(self, owner_id: str):
        """
        Downgrade an account from premium to free.

        This will:
        1. Update the account status to 'free'
        2. Freeze all but the most recent 2 sheet APIs
        """
        # Get the account to verify it exists
        account = self.get_account(owner_id)
        if not account:
            raise UserNotFoundError(f"Account with ID {owner_id} not found")

        # First update the account status to 'free'
        self.update_account(owner_id, {"account_status": "free"})

        # Get all sheet APIs for this account and sort sheets (newest first)
        sheets = self.get_sheet_apis_for_account(owner_id)
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
                        sheet_item = self.get_sheet_api_metadata(
                            owner_id=owner_id, sheet_api_id=sheet_api_name
                        )
                        # Update the frozen status
                        sheet_item["frozen"] = True
                        sheet_item["refresh_token_info"] = sheet_item[
                            "refresh_token_info"
                        ].to_dict()

                        update_requests.append({"PutRequest": {"Item": sheet_item}})
                    except SheetApiNotFoundError as error:
                        sentry_sdk.capture_exception(error)

            self.client.meta.client.batch_write_item(
                RequestItems={self.table_name: update_requests}
            )
            frozen_count += len(update_requests)

        return {
            "account_id": owner_id,
            "account_type": account.get("type"),
            "new_status": "free",
            "sheets_frozen": frozen_count,
            "active_sheets": min(len(sorted_sheets), 2),
        }

    def upgrade_account(self, owner_id: str):
        """
        Upgrade an account from free to premium.
        This will:
        1. Update the account status to 'premium'
        2. Unfreeze all sheet APIs
        """
        account = self.get_account(owner_id)
        if not account:
            raise UserNotFoundError(f"Account with ID {owner_id} not found")

        # First update the account status to 'premium'
        self.update_account(owner_id, {"account_status": "premium"})

        # Get all sheet APIs for this account
        sheets = self.get_sheet_apis_for_account(owner_id)

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
                            sheet_item = self.get_sheet_api_metadata(
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

        return {
            "account_id": owner_id,
            "account_type": account.get("type"),
            "new_status": "premium",
            "sheets_unfrozen": unfrozen_count,
            "total_sheets": len(sheets),
        }

    def get_accounts_by_billing_date(self, billing_end_date: str):
        """Get all accounts who's billing is due on the specified date

        Args:
            billing_end_date: must be YYYY-MM-DD
        """
        gsi4_pk = f"ACCOUNT#BILLING_END#{billing_end_date}"
        response = self.table.query(
            IndexName="GSI4",
            KeyConditionExpression="GSI4PK = :billing_pk",
            ExpressionAttributeValues={":billing_pk": gsi4_pk},
        )

        return response.get("Items", [])

    def _check_org_exists(self, org_id: str):
        user_or_org = self.get_account(org_id)
        if not user_or_org or user_or_org.get("type") != "organization":
            raise OrganizationNotFoundError(f"Organization with ID {org_id} not found")

    def _check_user_exists(self, user_id: str):
        user_or_org = self.get_account(user_id)
        if not user_or_org or user_or_org.get("type") != "user":
            raise UserNotFoundError(f"User with ID {user_id} not found")

    def _create_unique_sheet_api_key(self, owner_id: str):
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
