"""Shared test fixtures and configuration."""

import os
from collections.abc import Generator
from datetime import datetime

import boto3
import pytest
from moto import mock_aws
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import Account, RefreshTokenInfo
from jedwal.apis.models import Api, ApiCreate


@pytest.fixture(scope="function")
def aws_credentials():
    """Mock AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def dynamodb_table(aws_credentials) -> Generator[Table]:
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-table",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI2PK", "AttributeType": "S"},
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
                {"AttributeName": "GSI3PK", "AttributeType": "S"},
                {"AttributeName": "GSI3SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI2",
                    "KeySchema": [
                        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "GSI3",
                    "KeySchema": [
                        {"AttributeName": "GSI3PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI3SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


@pytest.fixture
def sample_refresh_token_info() -> RefreshTokenInfo:
    """Create a sample RefreshTokenInfo for testing."""
    return RefreshTokenInfo(
        encrypted_refresh_token="encrypted_token_data",
        data_encryption_key="encryption_key",
        context={"user_id": "test-user"},
    )


@pytest.fixture
def sample_account(sample_refresh_token_info) -> Account:
    """Create a sample Account for testing."""
    return Account(
        account_id="test-user-123",
        email="test@example.com",
        display_name="Test User",
        given_name="Test",
        family_name="User",
        account_status="premium",
        refresh_token_info=sample_refresh_token_info,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def sample_free_account(sample_refresh_token_info) -> Account:
    """Create a sample free Account for testing."""
    return Account(
        account_id="g122343f324242",
        email="free@example.com",
        display_name="Free User",
        given_name="Free",
        family_name="User",
        account_status="free",
        refresh_token_info=sample_refresh_token_info,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def sample_api(sample_refresh_token_info) -> Api:
    """Create a sample Api for testing."""
    return Api(
        api_key="test-api-key",
        owner_id="test-user-123",
        google_sheet_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        refresh_token_info=sample_refresh_token_info,
        frozen=False,
        cache_duration=3600,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def sample_api_create(sample_refresh_token_info) -> ApiCreate:
    return ApiCreate(
        google_sheet_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        cache_duration=3600,
        frozen=False,
        owner_id="test-user-123",
        refresh_token_info=sample_refresh_token_info,
    )
