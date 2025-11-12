"""Unit tests for billing repository layer."""

from datetime import UTC, datetime

import pytest

from jedwal.billing import repository
from jedwal.billing.models import BillingInfo
from jedwal.common.exceptions import NotFoundException


def test_to_billing_item_with_all_fields(sample_billing_info):
    """Test converting BillingInfo to DynamoDB item with all fields populated."""
    item = repository.to_billing_item(billing_info=sample_billing_info)

    assert item["billing_start"] == "2025-01-01T00:00:00+00:00"
    assert item["billing_end"] == "2025-02-01T00:00:00+00:00"
    assert item["GSI4PK"] == "ACCOUNT#BILLING_END#2025-02-01"
    assert item["stripe_customer_id"] == "cus_test123"
    assert item["stripe_subscription_id"] == "sub_test456"


def test_to_billing_item_with_optional_fields_missing():
    """Test converting BillingInfo with None values omits those fields.

    Note: account_id is never included in the return value because it's used
    for the Key in update_item operations, not in the update fields.
    """
    billing_info = BillingInfo(
        account_id="test-user-123",
        billing_start=None,
        billing_end=None,
        stripe_customer_id=None,
        stripe_subscription_id=None,
    )

    item = repository.to_billing_item(billing_info=billing_info)

    # Empty dict when all fields are None
    assert item == {}


def test_to_billing_item_with_partial_fields():
    """Test converting BillingInfo with some fields populated."""
    billing_info = BillingInfo(
        account_id="test-user-123",
        billing_start=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        billing_end=datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
        stripe_customer_id=None,
        stripe_subscription_id=None,
    )

    item = repository.to_billing_item(billing_info=billing_info)

    assert "billing_start" in item
    assert "billing_end" in item
    assert "GSI4PK" in item
    assert "stripe_customer_id" not in item
    assert "stripe_subscription_id" not in item


def test_to_billing_info_from_complete_item():
    """Test converting complete DynamoDB item to BillingInfo."""
    item = {
        "account_id": "test-user-123",
        "billing_start": "2025-01-01T00:00:00+00:00",
        "billing_end": "2025-02-01T00:00:00+00:00",
        "stripe_customer_id": "cus_test123",
        "stripe_subscription_id": "sub_test456",
    }

    billing_info = repository.to_billing_info(item=item)

    assert billing_info.account_id == "test-user-123"
    assert billing_info.billing_start == datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert billing_info.billing_end == datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC)
    assert billing_info.stripe_customer_id == "cus_test123"
    assert billing_info.stripe_subscription_id == "sub_test456"


def test_to_billing_info_from_item_with_missing_fields():
    """Test converting DynamoDB item with missing optional fields."""
    item = {
        "account_id": "test-user-123",
        # No billing dates or Stripe IDs
    }

    billing_info = repository.to_billing_info(item=item)

    assert billing_info.account_id == "test-user-123"
    assert billing_info.billing_start is None
    assert billing_info.billing_end is None
    assert billing_info.stripe_customer_id is None
    assert billing_info.stripe_subscription_id is None


def test_round_trip_transformation(sample_billing_info):
    """Test that BillingInfo -> item -> BillingInfo preserves data."""
    # Convert to item
    item = repository.to_billing_item(billing_info=sample_billing_info)

    # Add account_id (would be in DB but not in partial update item)
    item["account_id"] = sample_billing_info.account_id

    # Convert back
    result = repository.to_billing_info(item=item)

    assert result.account_id == sample_billing_info.account_id
    assert result.billing_start == sample_billing_info.billing_start
    assert result.billing_end == sample_billing_info.billing_end
    assert result.stripe_customer_id == sample_billing_info.stripe_customer_id
    assert result.stripe_subscription_id == sample_billing_info.stripe_subscription_id


def test_update_billing_info_creates_fields(
    dynamodb_table, sample_account, sample_billing_info
):
    """Test updating billing info on an existing account."""
    from jedwal.account import repository as account_repo

    # Create an account first
    account_repo.create_account(table=dynamodb_table, account=sample_account)

    # Update billing info
    result = repository.update_billing_info(
        table=dynamodb_table, billing_info=sample_billing_info
    )

    assert result.account_id == "test-user-123"

    # Verify it was saved
    retrieved = repository.get_billing_info(
        table=dynamodb_table, account_id="test-user-123"
    )

    assert retrieved is not None
    assert retrieved.billing_start == sample_billing_info.billing_start
    assert retrieved.billing_end == sample_billing_info.billing_end
    assert retrieved.stripe_customer_id == "cus_test123"


def test_update_billing_info_account_not_found(dynamodb_table):
    """Test updating billing info for nonexistent account raises NotFoundException."""
    billing_info = BillingInfo(
        account_id="nonexistent-user",
        billing_start=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        billing_end=datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
    )

    with pytest.raises(
        NotFoundException, match="Account with id nonexistent-user not found"
    ):
        repository.update_billing_info(table=dynamodb_table, billing_info=billing_info)


def test_get_billing_info_nonexistent_account(dynamodb_table):
    """Test getting billing info for nonexistent account returns None."""
    result = repository.get_billing_info(table=dynamodb_table, account_id="nonexistent")

    assert result is None


def test_get_accounts_by_billing_end_date(
    dynamodb_table, sample_account, sample_free_account
):
    """Test querying accounts by billing end date."""
    from jedwal.account import repository as account_repo

    # Create two accounts
    account_repo.create_account(table=dynamodb_table, account=sample_account)
    account_repo.create_account(table=dynamodb_table, account=sample_free_account)

    # Set billing info for first account (ends Feb 1)
    billing_info_1 = BillingInfo(
        account_id="test-user-123",
        billing_start=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        billing_end=datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
        stripe_customer_id="cus_test123",
    )
    repository.update_billing_info(table=dynamodb_table, billing_info=billing_info_1)

    # Set billing info for second account (ends Feb 15)
    billing_info_2 = BillingInfo(
        account_id="g122343f324242",
        billing_start=datetime(2025, 1, 15, 0, 0, 0, tzinfo=UTC),
        billing_end=datetime(2025, 2, 15, 0, 0, 0, tzinfo=UTC),
        stripe_customer_id="cus_test456",
    )
    repository.update_billing_info(table=dynamodb_table, billing_info=billing_info_2)

    # Query for accounts ending Feb 1
    results = repository.get_accounts_by_billing_end_date(
        table=dynamodb_table, billing_end_date="2025-02-01"
    )

    assert len(results) == 1
    assert results[0].account_id == "test-user-123"
    assert results[0].stripe_customer_id == "cus_test123"

    # Query for accounts ending Feb 15
    results = repository.get_accounts_by_billing_end_date(
        table=dynamodb_table, billing_end_date="2025-02-15"
    )

    assert len(results) == 1
    assert results[0].account_id == "g122343f324242"


def test_get_accounts_by_billing_end_date_no_results(dynamodb_table):
    """Test querying with date that has no matches returns empty list."""
    results = repository.get_accounts_by_billing_end_date(
        table=dynamodb_table, billing_end_date="2025-12-31"
    )

    assert results == []


def test_update_billing_info_with_empty_fields(dynamodb_table, sample_account):
    """Test updating billing info with all None values does nothing."""
    from jedwal.account import repository as account_repo

    # Create account
    account_repo.create_account(table=dynamodb_table, account=sample_account)

    # Try to update with all None values
    billing_info = BillingInfo(
        account_id="test-user-123",
        billing_start=None,
        billing_end=None,
        stripe_customer_id=None,
        stripe_subscription_id=None,
    )

    result = repository.update_billing_info(
        table=dynamodb_table, billing_info=billing_info
    )

    # Should return the billing_info without errors
    assert result.account_id == "test-user-123"
