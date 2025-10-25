from collections import defaultdict
from datetime import datetime
from typing import Any, Literal, Optional


import boto3
from boto3.resources.base import ServiceResource
from botocore.exceptions import ClientError
import randomname


from sheetsapi.account_repo import AccountRepo
from sheetsapi.config import Config
from sheetsapi.models.domain_models import RefreshTokenInfo
from sheetsapi.models.db_models import DocApi
from sheetsapi.image_handler import ImageHandler

AccountType = Literal["user", "organization"]
AccountStatus = Literal["free", "premium"]
MemberType = Literal["owner", "member"]


class UserNotFoundError(Exception):
    """Thrown if requested user doesn't exist"""


class SheetNameTakenError(Exception):
    """"""


class DocApiNotFoundError(Exception):
    """Sheet for key not found"""


class DocApiRepo:
    def __init__(
        self,
        client,
        table_name: str,
        account_repo: AccountRepo,
        image_handler: ImageHandler,
    ):
        self.client = client
        self.table_name = table_name
        self.account_repo = account_repo
        self.image_handler = image_handler

    @property
    def table(self) -> ServiceResource:
        return self.client.Table(self.table_name)

    @classmethod
    def from_table_name(cls, table_name: str = Config.Constants.SHEETS_API_TABLE):
        client = boto3.resource("dynamodb", region_name=Config.Constants.AWS_REGION)
        account_repo = AccountRepo.from_table_name(
            table_name=Config.Constants.SHEETS_API_TABLE
        )
        image_handler = ImageHandler()
        return DocApiRepo(client, table_name, account_repo, image_handler)

    def delete_api(self, owner_id: str, api_name: str):
        """Delete a sheet API and all its analytics records."""
        sheet_api_key = f"DOC#{owner_id}#{api_name}"

        deleted_items = defaultdict(int)

        # Check sheet API exists. This will throw if doesn't exist
        deleted_items["apis"] += 1
        self.table.delete_item(Key={"PK": sheet_api_key, "SK": sheet_api_key})

        # Batch delete all analytics records
        analytics_results = self.table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": f"ANALYTICS#{owner_id}#{api_name}"},
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

    def get_api_metadata(self, owner_id: str, sheet_api_id: str) -> DocApi:
        """Get metadata for a specific sheet API"""

        key = f"DOC#{owner_id}#{sheet_api_id}"
        result = self.table.get_item(Key={"PK": key, "SK": key})
        item = result.get("Item")
        if item is None:
            raise DocApiNotFoundError(f"Sheet not found with key {key}")

        item["categories"] = self._get_categories_for_api(owner_id, sheet_api_id)
        return DocApi.from_dict(item)

    def get_apis_for_account(self, owner_id: str) -> list[DocApi]:
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
                ":resource_type": f"DOC#",
            },
        )
        items = response.get("Items", [])
        apis = []
        for item in items:
            api_name = item["doc_api_name"]
            item["categories"] = self._get_categories_for_api(owner_id, api_name)
            apis.append(DocApi.from_dict(item))
        return apis

    def get_api_by_google_doc_id(self, owner_id, google_sheet_id):
        """Find a doc API by Google Sheet ID for a specific owner."""
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

        return DocApi.from_dict(items[0])

    def update_api(
        self,
        owner_id: str,
        api_name: str,
        fields: dict[str, Any],
    ):
        """Update a sheet API with the provided fields."""
        api_key = f"DOC#{owner_id}#{api_name}"

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
            return self.get_api_metadata(owner_id, api_name)

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

            item = response.get("Attributes")
            return DocApi.from_dict(item)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise DocApiNotFoundError(f"Sheet API not found: {api_key}")
            raise

    def add_category_to_api(self, owner_id: str, doc_api: str, category: str):
        items = [
            {
                # Forward relationship: Category -> API
                "PK": f"CATEGORY#{owner_id}#{category}",
                "SK": f"API#{doc_api}",
                "GSI1PK": f"API#{doc_api}",  # For reverse lookup
                "GSI1SK": f"CATEGORY#{category}",
                "owner_id": owner_id,
                "relationship_type": "category_to_api",
            },
            {
                # Reverse relationship: API -> Category
                "PK": f"API#{owner_id}#{doc_api}",
                "SK": f"CATEGORY#{category}",
                "GSI1PK": f"CATEGORY#{owner_id}#{category}",  # For forward lookup
                "GSI1SK": f"API#{doc_api}",
                "owner_id": owner_id,
                "relationship_type": "api_to_category",
            },
        ]

        # Use batch write or transaction
        with self.table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    def delete_category_from_api(self, owner_id: str, doc_api: str, category: str):
        """Delete the relationship between a category and an API"""

        # Define the two items to delete (both sides of the relationship)
        keys_to_delete = [
            {
                # Forward relationship: Category -> API
                "PK": f"CATEGORY#{owner_id}#{category}",
                "SK": f"API#{doc_api}",
            },
            {
                # Reverse relationship: API -> Category
                "PK": f"API#{owner_id}#{doc_api}",
                "SK": f"CATEGORY#{category}",
            },
        ]

        # Use batch write to delete both items atomically
        with self.table.batch_writer() as batch:
            for key in keys_to_delete:
                batch.delete_item(Key=key)

    def create_api(
        self,
        owner_id,
        google_doc_id: str,
        refresh_token_info: RefreshTokenInfo,
        payload: dict,
        ast_payload: str,
        title: str,
        creator: str,
        doc_api_name: Optional[str] = None
    ) -> DocApi:
        """Create a new sheet API"""
        if self.account_repo.get_account(owner_id) is None:
            raise UserNotFoundError("User or org does not exist to create sheet API")
        existing_api = self.get_api_by_google_doc_id(owner_id, google_doc_id)
        if existing_api is not None:
            return existing_api

        if doc_api_name is None:
            doc_api_key = self._create_unique_doc_pk(owner_id)
        else:
            doc_api_key = f"DOC#{owner_id}#{doc_api_name}"
        
        api_name = doc_api_key.split("#")[2]
        published_at = datetime.now().isoformat()

        item = DocApi(
            PK=doc_api_key,
            SK=doc_api_key,
            doc_api_name=api_name,
            owner_id=owner_id,
            google_doc_id=google_doc_id,
            google_doc_payload=payload,
            google_doc_ast=ast_payload,
            refresh_token_info=refresh_token_info,
            frozen=False,
            created_at=datetime.now().isoformat(),
            GSI2PK=f"ACCOUNT#{owner_id}",
            GSI2SK=doc_api_key,
            title=title,
            published_at=published_at,
            creator=creator,
        )

        try:
            self.table.put_item(
                Item=item.model_dump(),
                ConditionExpression="attribute_not_exists(PK)",
            )
            return item
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise SheetNameTakenError(
                    f"Sheet API with key {doc_api_key} already exists"
                )
            raise

    def check_if_name_available(self, owner_id, doc_api_name) -> bool:
        key = f"DOC#{owner_id}#{doc_api_name}"
        res = self.table.get_item(Key={"PK": key, "SK": key})
        return res.get("Item") is None

    def _create_unique_doc_pk(self, owner_id: str):
        """Create a unique key for a sheet API."""

        def key_exists(key):
            res = self.table.get_item(Key={"PK": key, "SK": key})
            return res.get("Item") is not None

        name = randomname.get_name()
        key = f"DOC#{owner_id}#{name}"

        while key_exists(key):
            name = randomname.get_name()
            key = f"DOC#{owner_id}#{name}"
        return key

    def _get_categories_for_api(self, owner_id: str, sheet_api_id: str) -> list[str]:
        """Get all categories for a specific API using adjacency list pattern"""

        # Query the API -> Category relationships
        pk = f"API#{owner_id}#{sheet_api_id}"

        response = self.table.query(
            KeyConditionExpression="PK = :pk", ExpressionAttributeValues={":pk": pk}
        )

        categories = []
        for item in response.get("Items", []):
            # SK format is "CATEGORY#{category}"
            sk = item["SK"]
            if sk.startswith("CATEGORY#"):
                category = sk.replace("CATEGORY#", "")
                categories.append(category)

        return categories
