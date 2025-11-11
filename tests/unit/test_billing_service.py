"""Unit tests for billing service layer."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from jedwal.billing import service
from jedwal.billing.models import BillingInfo
from jedwal.common.exceptions import NotFoundException


@patch("jedwal.billing.service.stripe_client")
@patch("jedwal.billing.service.account_service")
def test_handle_checkout_completed_upgrades_and_sets_billing(
    mock_account_service, mock_stripe_client, dynamodb_table, sample_account
):
    """Test that checkout completed upgrades user and sets billing period."""
    from jedwal.account import repository as account_repo

    # Create account in DB
    account_repo.create_account(table=dynamodb_table, account=sample_account)

    # Mock Stripe returning billing period
    mock_stripe_client.get_subscription_period.return_value = (
        datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
    )

    # Mock account service returning account
    mock_account_service.get_account_by_email.return_value = sample_account

    # Call the handler
    service.handle_checkout_completed(
        table=dynamodb_table,
        customer_email="test@example.com",
        customer_id="cus_test123",
        subscription_id="sub_test456",
    )

    # Verify account service was called to upgrade
    mock_account_service.update_account.assert_called_once()
    updated_account = mock_account_service.update_account.call_args[1]["account"]
    assert updated_account.account_status == "premium"

    # Verify billing info was saved
    from jedwal.billing import repository

    billing_info = repository.get_billing_info(
        table=dynamodb_table, account_id="test-user-123"
    )

    assert billing_info is not None
    assert billing_info.billing_start == datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert billing_info.billing_end == datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC)
    assert billing_info.stripe_customer_id == "cus_test123"
    assert billing_info.stripe_subscription_id == "sub_test456"


@patch("jedwal.billing.service.stripe_client")
@patch("jedwal.billing.service.account_service")
def test_handle_invoice_paid_extends_billing_period(
    mock_account_service, mock_stripe_client, dynamodb_table, sample_account
):
    """Test that invoice paid extends the billing period for next cycle."""
    from jedwal.account import repository as account_repo
    from jedwal.billing import repository as billing_repo

    # Create account in DB
    account_repo.create_account(table=dynamodb_table, account=sample_account)

    # Set initial billing period (ending Feb 1)
    initial_billing = BillingInfo(
        account_id="test-user-123",
        billing_start=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        billing_end=datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
        stripe_customer_id="cus_test123",
        stripe_subscription_id="sub_test456",
    )
    billing_repo.update_billing_info(table=dynamodb_table, billing_info=initial_billing)

    # Mock Stripe returning new billing period (Feb 1 - Mar 1)
    mock_stripe_client.get_subscription_period.return_value = (
        datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
        datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC),
    )

    # Mock Stripe subscription and customer
    mock_subscription = MagicMock()
    mock_subscription.customer = "cus_test123"
    mock_stripe_client.get_subscription.return_value = mock_subscription

    mock_customer = MagicMock()
    mock_customer.email = "test@example.com"
    mock_stripe_client.get_customer.return_value = mock_customer

    # Mock account service
    mock_account_service.get_account_by_email.return_value = sample_account

    # Call the handler
    service.handle_invoice_paid(table=dynamodb_table, subscription_id="sub_test456")

    # Verify billing period was updated
    billing_info = billing_repo.get_billing_info(
        table=dynamodb_table, account_id="test-user-123"
    )

    assert billing_info.billing_start == datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC)
    assert billing_info.billing_end == datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC)


@patch("jedwal.billing.service.stripe_client")
@patch("jedwal.billing.service.account_service")
def test_handle_subscription_deleted_downgrades_user(
    mock_account_service, mock_stripe_client, dynamodb_table, sample_account
):
    """Test that subscription deleted downgrades user to free tier."""
    from jedwal.account import repository as account_repo

    # Create premium account
    account_repo.create_account(table=dynamodb_table, account=sample_account)

    # Mock Stripe customer
    mock_customer = MagicMock()
    mock_customer.email = "test@example.com"
    mock_stripe_client.get_customer.return_value = mock_customer

    # Mock account service
    mock_account_service.get_account_by_email.return_value = sample_account

    # Call the handler
    service.handle_subscription_deleted(table=dynamodb_table, customer_id="cus_test123")

    # Verify account service was called to downgrade
    mock_account_service.update_account.assert_called_once()
    updated_account = mock_account_service.update_account.call_args[1]["account"]
    assert updated_account.account_status == "free"


@patch("jedwal.billing.service.stripe_client")
def test_create_checkout_session_returns_url(
    mock_stripe_client, dynamodb_table, sample_account
):
    """Test creating checkout session returns Stripe URL."""
    from jedwal.account import repository as account_repo

    # Create account
    account_repo.create_account(table=dynamodb_table, account=sample_account)

    # Mock Stripe customer
    mock_customer = MagicMock()
    mock_customer.id = "cus_test123"
    mock_stripe_client.get_or_create_customer.return_value = mock_customer

    # Mock checkout session
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/session123"
    mock_stripe_client.create_checkout_session.return_value = mock_session

    # Call service
    result = service.create_checkout_session(
        table=dynamodb_table,
        account_id="test-user-123",
        success_url="https://app.com/success",
        cancel_url="https://app.com/cancel",
    )

    assert result.url == "https://checkout.stripe.com/session123"

    # Verify Stripe was called correctly
    mock_stripe_client.get_or_create_customer.assert_called_once_with(
        email="test@example.com"
    )
    mock_stripe_client.create_checkout_session.assert_called_once_with(
        customer_id="cus_test123",
        success_url="https://app.com/success",
        cancel_url="https://app.com/cancel",
    )


def test_create_checkout_session_account_not_found(dynamodb_table):
    """Test creating checkout for nonexistent account raises NotFoundException."""
    with pytest.raises(NotFoundException, match="Account not found"):
        service.create_checkout_session(
            table=dynamodb_table,
            account_id="nonexistent",
            success_url="https://app.com/success",
            cancel_url="https://app.com/cancel",
        )


@patch("jedwal.billing.service.stripe_client")
@patch("jedwal.billing.service.account_service")
def test_handle_checkout_completed_idempotent(
    mock_account_service, mock_stripe_client, dynamodb_table, sample_account
):
    """Test that handling the same checkout event twice doesn't break."""
    from jedwal.account import repository as account_repo

    # Create account
    account_repo.create_account(table=dynamodb_table, account=sample_account)

    # Mock Stripe
    mock_stripe_client.get_subscription_period.return_value = (
        datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
    )
    mock_account_service.get_account_by_email.return_value = sample_account

    # Call handler twice with same data
    for _ in range(2):
        service.handle_checkout_completed(
            table=dynamodb_table,
            customer_email="test@example.com",
            customer_id="cus_test123",
            subscription_id="sub_test456",
        )

    # Should still have correct billing info (last write wins)
    from jedwal.billing import repository

    billing_info = repository.get_billing_info(
        table=dynamodb_table, account_id="test-user-123"
    )

    assert billing_info is not None
    assert billing_info.stripe_customer_id == "cus_test123"


def test_get_accounts_by_billing_end_date(
    dynamodb_table, sample_account, sample_free_account
):
    """Test getting accounts by billing end date through service."""
    from jedwal.account import repository as account_repo
    from jedwal.billing import repository as billing_repo

    # Create accounts
    account_repo.create_account(table=dynamodb_table, account=sample_account)
    account_repo.create_account(table=dynamodb_table, account=sample_free_account)

    # Set billing for both accounts with same end date
    end_date = datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC)

    billing_1 = BillingInfo(
        account_id="test-user-123",
        billing_start=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        billing_end=end_date,
    )
    billing_repo.update_billing_info(table=dynamodb_table, billing_info=billing_1)

    billing_2 = BillingInfo(
        account_id="g122343f324242",
        billing_start=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        billing_end=end_date,
    )
    billing_repo.update_billing_info(table=dynamodb_table, billing_info=billing_2)

    # Query through service
    results = service.get_accounts_by_billing_end_date(
        table=dynamodb_table, end_date="2025-02-01"
    )

    assert len(results) == 2
    account_ids = [r.account_id for r in results]
    assert "test-user-123" in account_ids
    assert "g122343f324242" in account_ids
