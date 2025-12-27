"""Billing service layer for business logic."""

import logging

from jedwal.account import service as account_service
from jedwal.account.models import AccountId
from jedwal.billing import repository, stripe_client
from jedwal.billing.models import BillingInfo, CheckoutSession
from jedwal.common.exceptions import NotFoundException
from jedwal.database.core import DbTable

logger = logging.getLogger(__name__)


def create_checkout_session(
    *, table: DbTable, account_id: AccountId, success_url: str, cancel_url: str
) -> CheckoutSession:
    """Create a Stripe checkout session for premium subscription.

    Args:
        table: DynamoDB table
        account_id: Account ID requesting checkout
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if user cancels

    Returns:
        CheckoutSession with checkout URL
    """
    account = account_service.get_account(table=table, id=account_id)

    if account is None:
        raise NotFoundException(
            detail=[{"msg": "Account not found for checkout creation"}]
        )

    customer = stripe_client.get_or_create_customer(email=account.email)
    session = stripe_client.create_checkout_session(
        customer_id=customer.id,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return CheckoutSession(url=session.url)


def handle_checkout_completed(
    *, table: DbTable, customer_email: str, customer_id: str, subscription_id: str
) -> None:
    """Handle successful checkout - upgrade user and set billing period.

    Args:
        table: DynamoDB table
        customer_email: Customer's email from Stripe
        customer_id: Stripe customer ID
        subscription_id: Stripe subscription ID
    """
    from jedwal.apis import service as apis_service
    from jedwal.posts import service as posts_service

    # Get subscription period from Stripe
    start, end = stripe_client.get_subscription_period(subscription_id=subscription_id)

    # Get account
    account = account_service.get_account_by_email(table=table, email=customer_email)

    # Upgrade to premium
    account_service.update_account(
        table=table,
        account=account.model_copy(update={"account_status": "premium"}),
    )

    # Update billing info
    billing_info = BillingInfo(
        account_id=account.account_id,
        billing_start=start,
        billing_end=end,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
    )
    repository.update_billing_info(table=table, billing_info=billing_info)
    posts_service.unfreeze_posts_for_account(table=table, owner_id=account.account_id)
    apis_service.unfreeze_apis_for_account(table=table, owner_id=account.account_id)

    logger.info(f"Upgraded account {account.account_id} to premium")


def handle_invoice_paid(*, table: DbTable, subscription_id: str) -> None:
    """Handle invoice paid - update billing period for next cycle.

    Args:
        table: DynamoDB table
        subscription_id: Stripe subscription ID
    """
    # Get updated subscription period
    start, end = stripe_client.get_subscription_period(subscription_id=subscription_id)

    # Get subscription to find customer
    subscription = stripe_client.get_subscription(subscription_id=subscription_id)
    customer = stripe_client.get_customer(customer_id=subscription.customer)

    # Update billing period
    account = account_service.get_account_by_email(table=table, email=customer.email)
    billing_info = BillingInfo(
        account_id=account.account_id,
        billing_start=start,
        billing_end=end,
    )
    repository.update_billing_info(table=table, billing_info=billing_info)

    logger.info(f"Updated billing period for account {account.account_id}")


def handle_subscription_deleted(*, table: DbTable, customer_id: str) -> None:
    """Handle subscription cancellation - downgrade user to free.

    Args:
        table: DynamoDB table
        customer_id: Stripe customer ID
    """
    from jedwal.apis import service as apis_service
    from jedwal.posts import service as posts_service

    customer = stripe_client.get_customer(customer_id=customer_id)
    account = account_service.get_account_by_email(table=table, email=customer.email)

    account_service.update_account(
        table=table,
        account=account.model_copy(update={"account_status": "free"}),
    )
    posts_service.freeze_posts_for_account(table=table, owner_id=account.account_id)
    apis_service.freeze_apis_for_account(table=table, owner_id=account.account_id)


def get_accounts_by_billing_end_date(*, table: DbTable, end_date: str):
    return repository.get_accounts_by_billing_end_date(
        table=table, billing_end_date=end_date
    )
