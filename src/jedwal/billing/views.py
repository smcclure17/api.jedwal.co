"""Billing API endpoints."""

import logging

from fastapi import APIRouter, Header, HTTPException
from starlette.requests import Request

from jedwal.auth.service import CurrentAccount
from jedwal.billing import service, stripe_client
from jedwal.billing.models import CheckoutSession
from jedwal.config.config import settings
from jedwal.database.core import DbTable

logger = logging.getLogger(__name__)
billing_router = APIRouter(prefix="/billing", tags=["billing"])


@billing_router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    table: DbTable,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
):
    """Handle Stripe webhook events.

    Processes events such as:
    - checkout.session.completed: Upgrade user to premium
    - invoice.paid: Update billing period for renewal
    - customer.subscription.deleted: Downgrade user from premium
    """
    payload = await request.body()

    # Verify webhook signature
    event = stripe_client.verify_webhook_signature(
        payload=payload, signature=stripe_signature
    )

    event_type = event["type"]

    try:
        if event_type == "checkout.session.completed":
            service.handle_checkout_completed(
                table=table,
                customer_email=event.data.object["customer_details"]["email"],
                customer_id=event.data.object["customer"],
                subscription_id=event.data.object["subscription"],
            )
        elif event_type == "invoice.paid":
            subscription_id = event.data.object.get("subscription")
            if subscription_id:  # Only process subscription invoices
                service.handle_invoice_paid(
                    table=table,
                    subscription_id=subscription_id,
                )
        elif event_type == "customer.subscription.deleted":
            service.handle_subscription_deleted(
                table=table,
                customer_id=event.data.object["customer"],
            )
        else:
            logger.info(f"Unhandled Stripe event: {event_type}")
    except Exception as e:
        logger.error(f"Error processing Stripe webhook {event_type}: {str(e)}")
        raise HTTPException(500, detail=f"Webhook processing failed: {str(e)}") from e

    return {"status": "success"}


@billing_router.post("/create-checkout", response_model=CheckoutSession)
async def create_checkout(
    table: DbTable,
    current_account: CurrentAccount,
):
    """Create a Stripe checkout session for premium subscription.

    Returns a URL to redirect the user to Stripe's checkout page.
    """
    checkout_session = service.create_checkout_session(
        table=table,
        account_id=current_account.account_id,
        success_url=f"{settings.client_base_url}/return?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.client_base_url}/cancel",
    )
    return checkout_session
