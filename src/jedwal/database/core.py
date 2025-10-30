"""DynamoDB connection and client management."""

from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Attr, Key

from jedwal.config import settings


@lru_cache
def get_dynamodb_resource():
    """
    Get cached DynamoDB resource.

    In Lambda, credentials are automatically provided via IAM execution role.
    endpoint_url is only used for local development with DynamoDB Local.
    """
    config = {"region_name": settings.aws_region}

    # Only set endpoint_url for local development
    if settings.dynamodb_endpoint_url:
        config["endpoint_url"] = settings.dynamodb_endpoint_url

    return boto3.resource("dynamodb", **config)


def get_table(table_name: str):
    """
    Get a DynamoDB table instance.

    Functional approach - simply returns the table resource.

    Args:
        table_name: Direct table name (e.g., from settings.sheets_api_table)

    Returns:
        DynamoDB Table resource

    Example:
        table = get_table(settings.sheets_api_table)
        response = table.get_item(Key={"id": "123"})
    """
    dynamodb = get_dynamodb_resource()
    return dynamodb.Table(table_name)


# Export condition helpers for easy imports
__all__ = [
    "get_dynamodb_resource",
    "get_table",
    "Key",
    "Attr",
]
