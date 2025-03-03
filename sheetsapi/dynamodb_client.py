from typing import Dict, List, Any, Optional

import boto3
from boto3.dynamodb.conditions import Key
from sheetsapi.config import Config

class ItemNotFound(Exception):
    """Raised when the specified item does not exist in the repo."""


class DynamoDBClient:
    """Generic client for interacting with DynamoDB."""

    def __init__(self, client=None):
        self._client = client or boto3.resource(
            "dynamodb", region_name=Config.Constants.AWS_REGION
        )

    def get_item(self, table: str, key: Dict[str, Any]) -> Optional[Dict[Any, Any]]:
        """Get single item from table.

        Args:
            table: Table name
            key: Key to query table with. Should be in form {'<attribute name>': <attribute value>}.

        Returns: Row if exists, None if missing.
        """
        table = self._client.Table(table)
        result = table.get_item(Key=key)

        if "Item" not in result:
            return None

        return result["Item"]

    def query_index(
        self,
        table: str,
        index: str | None,
        key: str,
        value: Any,
        limit: int = None,
        KeyConditionExpression: str = None,
        ExpressionAttributeValues: Dict[str, Any] = None,
    ) -> List[dict]:
        """Query index with extended functionality.
        
        Args:
            table: Table name.
            index: Index name.
            key: Key to query.
            value: value.
            limit: Optional maximum number of items to return
            KeyConditionExpression: Optional custom key condition
            ExpressionAttributeValues: Optional values for expression
        """
        table = self._client.Table(table)
        params = {}
        
        if index is not None:
            params["IndexName"] = index
            
        if KeyConditionExpression is not None:
            params["KeyConditionExpression"] = KeyConditionExpression
            params["ExpressionAttributeValues"] = {
                ":pk": value,
                **(ExpressionAttributeValues or {})
            }
        else:
            params["KeyConditionExpression"] = Key(key).eq(value)
            
        if limit is not None:
            params["Limit"] = limit

        result = table.query(**params)
        return result["Items"]

    def put_item(self, table: str, item: Dict[str, Any]) -> None:
        """Add item to table.

        Args:
            table: Table name.
            item: Item to add in form {'<attribute_name>': <attribute_value>, ...}.
        """
        table = self._client.Table(table)
        table.put_item(Item=item)

    def delete_item(self, table: str, key: Dict[str, Any]) -> None:
        table = self._client.Table(table)
        response = table.delete_item(Key=key, ReturnValues="ALL_OLD")

        if "Attributes" not in response:
            raise ItemNotFound(f"Cannot delete item that does not exist. Key: {key}")

    def _generic_query(self, table: str, params: dict) -> List[dict]:
        """Query table for items where `key` == `value`.

        Returns: List of rows matching query.
        """
        table = self._client.Table(table)
        result = table.query(**params)
        return result["Items"]

    def update_item(self, table: str, key: Dict[str, Any], item: Dict[str, Any]) -> Any:
        """Update an item with the given id.

        Keys in item that already exist will be updated, new keys will be added.
        """
        table = self._client.Table(table)

        if not self.get_item(Config.Constants.SHEETS_API_TABLE, key):
            raise ItemNotFound(f"Cannot update item that does not exist. Key: {key}")

        update_expression = []
        expression_attribute_values = {}
        expression_attribute_names = {}

        for k, v in item.items():
            if k != "id":  # Skip the partition key
                update_expression.append(f"#{k} = :{k}")
                expression_attribute_values[f":{k}"] = v
                expression_attribute_names[f"#{k}"] = k

        update_expression = "SET " + ", ".join(update_expression)

        response = table.update_item(
            Key=key,
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues="UPDATED_NEW",
        )
        return response

    def increment_item_field(
        self, table: str, key: Dict[str, Any], field: str, decrement=False
    ) -> Any:
        """Increment the count of a field in an item. Also allows decrementing."""
        table_obj = self._client.Table(table)

        # Check if the item exists
        if not self.get_item(table, key):
            raise ItemNotFound(
                f"Cannot increment field for an item that does not exist. Key: {key}"
            )

        adjustment_value = -1 if decrement else 1

        # Create the update expression
        update_expression = "SET #field = if_not_exists(#field, :zero) + :increment"

        # Define the expression attribute names and values
        expression_attribute_names = {"#field": field}
        expression_attribute_values = {":zero": 0, ":increment": adjustment_value}

        # Perform the update operation
        response = table_obj.update_item(
            Key=key,
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW",
        )
        return response

    def transact_write_items(self, items: List[Dict[str, Any]]) -> None:
        """Execute a transaction write with multiple items.
        
        Args:
            items: List of transaction items in the format expected by transact_write_items
        """
        self._client.meta.client.transact_write_items(
            TransactItems=items
        )
        
    def batch_get_items(self, table: str, keys: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get multiple items in a single request.
        
        Args:
            table: Table name
            keys: List of keys to fetch
        """
        table = self._client.Table(table)
        response = table.meta.client.batch_get_item(
            RequestItems={
                table.name: {
                    'Keys': keys
                }
            }
        )
        return response['Responses'][table.name]