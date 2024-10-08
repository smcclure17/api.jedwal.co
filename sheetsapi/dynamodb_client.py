from typing import Dict, List, Any, Optional

import boto3
from boto3.dynamodb.conditions import Key
from sheetsapi import config


class DynamoDBClient:
    """Generic client for interacting with DynamoDB."""

    def __init__(self, client=None):
        self._client = client or boto3.resource(
            "dynamodb", region_name=config.Config.Constants.AWS_REGION
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
        self, table: str, index: str | None, key: str, value: Any
    ) -> List[dict]:
        """Query index for items where `key` == `value`.

        Args:
            table: Table name.
            index: Index name.
            key: Key to query.
            value: value.

        Returns: List of rows matching query.
        """
        table = self._client.Table(table)
        if index is None:
            result = table.query(
                KeyConditionExpression=Key(key).eq(value)
            )  # query on primary key
        else:
            result = table.query(
                IndexName=index, KeyConditionExpression=Key(key).eq(value)
            )
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
            raise ValueError(f"Cannot delete item that does not exist. Key: {key}")

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

        if not self.get_item(config.Config.Constants.SHEETS_API_TABLE, key):
            raise ValueError(f"Cannot update item that does not exist. Key: {key}")

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
            raise ValueError(
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
