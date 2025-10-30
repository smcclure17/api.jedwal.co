"""Database module."""

from .core import Attr, Key, get_dynamodb_resource, get_table

__all__ = ["get_dynamodb_resource", "get_table", "Key", "Attr"]
