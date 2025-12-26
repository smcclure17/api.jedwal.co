"""Shared test fixtures and configuration."""

import os
from collections.abc import Generator
from datetime import UTC, datetime

# Set test environment variables BEFORE importing application code
# This ensures Settings loads test values instead of requiring .env file
os.environ.update(
    {
        # Application
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        # AWS Configuration
        "AWS_REGION": "us-east-1",
        # DynamoDB Tables
        "SHEETS_API_TABLE": "test-table",
        # Google OAuth
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "OAUTH_SECRET_TOKEN": "test-oauth-secret-token-for-sessions",
        # Sentry (disabled in tests)
        "SENTRY_DSN": "https://test@sentry.io/test",
        # Stripe (test keys)
        "STRIPE_SECRET_KEY": "sk_test_dummy",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_dummy",
        "STRIPE_SUBSCRIPTION_PRICE_ID": "price_test_subscription",
        "STRIPE_USAGE_BASED_PRICE_ID": "price_test_usage",
        # URLs
        "API_BASE_URL": "http://localhost:8000",
        "CLIENT_BASE_URL": "http://localhost:3000",
        "CLIENT_APP_BASE_URL": "http://localhost:3001",
        # Cookies
        "COOKIE_ALLOWED_DOMAIN": ".localhost",
        # CloudFront
        "CLOUDFRONT_DISTRIBUTION_ID": "TEST123456",
        # Encryption
        "ENCRYPTION_KEY_ID": "test-kms-key-id",
        # Email (disabled in tests)
        "EMAILS_ENABLED": "false",
        # Webhooks & Queues
        "WEBHOOK_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        # Image Storage
        "IMAGE_STORAGE_BUCKET": "test-images-bucket",
        "IMAGE_STORAGE_BUCKET_URL": "https://test-images-bucket.s3.us-east-1.amazonaws.com",
    }
)

import boto3
import pytest
from moto import mock_aws
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.account.models import Account, RefreshTokenInfo
from jedwal.apis.models import Api, ApiCreate
from jedwal.apis.worksheets.models import Worksheet, WorksheetCreate
from jedwal.billing.models import BillingInfo


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
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
                {"AttributeName": "GSI2PK", "AttributeType": "S"},
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
                {"AttributeName": "GSI3PK", "AttributeType": "S"},
                {"AttributeName": "GSI3SK", "AttributeType": "S"},
                {"AttributeName": "GSI4PK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
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
                {
                    "IndexName": "GSI4",
                    "KeySchema": [
                        {"AttributeName": "GSI4PK", "KeyType": "HASH"},
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


@pytest.fixture
def sample_worksheet() -> Worksheet:
    """Create a sample Worksheet for testing."""
    return Worksheet(
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
        data=[
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ],
        expires_at=datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC),
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_worksheet_create() -> WorksheetCreate:
    """Create a sample WorksheetCreate for testing."""
    return WorksheetCreate(
        owner_id="test-user-123",
        api_key="test-api-key",
        title="Sheet1",
        data=[
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ],
        expires_at=datetime(
            2030, 12, 31, 23, 59, 59, tzinfo=UTC
        ),  # Future date so cache is fresh
    )


@pytest.fixture
def sample_billing_info() -> BillingInfo:
    """Create a sample BillingInfo for testing."""
    return BillingInfo(
        account_id="test-user-123",
        billing_start=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        billing_end=datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
        stripe_customer_id="cus_test123",
        stripe_subscription_id="sub_test456",
    )
