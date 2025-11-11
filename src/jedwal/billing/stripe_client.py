"""Stripe API client wrapper."""

from datetime import UTC, datetime

import stripe

from jedwal.common.exceptions import BadRequestException, NotFoundException
from jedwal.config.config import settings

stripe.api_key = settings.stripe_secret_key


def verify_webhook_signature(*, payload: bytes, signature: str) -> stripe.Event:
    """Verify and construct Stripe webhook event."""
    try:
        return stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError as e:
        raise BadRequestException(f"Invalid Stripe signature: {str(e)}") from e


def get_or_create_customer(*, email: str) -> stripe.Customer:
    """Get existing Stripe customer or create new one."""
    customers = stripe.Customer.list(email=email, limit=1)
    if customers.data:
        return customers.data[0]
    return stripe.Customer.create(email=email)


def create_checkout_session(
    *, customer_id: str, success_url: str, cancel_url: str
) -> stripe.checkout.Session:
    """Create Stripe checkout session for subscription."""
    return stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price": settings.stripe_subscription_price_id,
                "quantity": 1,
            },
            {
                "price": settings.stripe_usage_based_price_id,
            },
        ],
        mode="subscription",
        customer=customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
    )


def get_subscription(*, subscription_id: str) -> stripe.Subscription:
    """Get Stripe subscription details."""
    return stripe.Subscription.retrieve(subscription_id)


def get_subscription_period(*, subscription_id: str) -> tuple[datetime, datetime]:
    """Get current billing period from subscription."""

    subscription = get_subscription(subscription_id=subscription_id)
    start = datetime.fromtimestamp(subscription.current_period_start, tz=UTC)
    end = datetime.fromtimestamp(subscription.current_period_end, tz=UTC)
    return start, end


def get_customer(*, customer_id: str) -> stripe.Customer:
    """Get Stripe customer by ID."""
    customer = stripe.Customer.retrieve(customer_id)
    if not customer or not customer.email:
        raise NotFoundException(
            f"Stripe customer {customer_id} not found or has no email"
        ) from None
    return customer


def report_usage_to_meter(*, customer_id: str, usage_quantity: int) -> None:
    """Report usage to Stripe billing meter for metered billing."""
    import uuid
    from datetime import datetime

    identifier = (
        f"{customer_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4()}"
    )

    stripe.billing.MeterEvent.create(
        event_name="data_refreshes",
        payload={"stripe_customer_id": customer_id, "value": usage_quantity},
        timestamp=int(datetime.now().timestamp()),
        identifier=identifier,
    )
