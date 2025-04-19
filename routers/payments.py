"""
Payment processing routes and webhook handlers.
"""

from datetime import datetime
import logging
import stripe
from fastapi import APIRouter, Header, HTTPException
from starlette.requests import Request

from dependencies import CurrentUser
from sheetsapi import config, stripe_helpers

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])


@router.post("/stripe-webhook")
async def webhook_received(request: Request, stripe_signature: str = Header(None)):
    """
    Handle Stripe webhook events.

    Processes events such as:
    - checkout.session.completed: Upgrade user to premium
    - customer.subscription.deleted: Downgrade user from premium

    Args:
        request: The request object containing the webhook payload
        stripe_signature: Stripe signature for verifying the webhook

    Returns:
        dict: Status response
    """
    data = await request.body()
    stripe_handler = stripe_helpers.StripeHandler()
    try:
        event = stripe_handler.get_event(payload=data, header=stripe_signature)
    except stripe.SignatureVerificationError as error:
        raise HTTPException(400, detail=str(error))

    event_type = event["type"]
    if event_type == "checkout.session.completed":
        user_email = event.data.object["customer_details"]["email"]
        customer_id = event.data.object["customer"]
        subscription_id = event.data.object["subscription"]
        subscription = stripe.Subscription.retrieve(subscription_id)
        current_period_start = datetime.fromtimestamp(subscription.current_period_start)
        current_period_end = datetime.fromtimestamp(subscription.current_period_end)

        stripe_handler.upgrade_user(user_email)
        stripe_handler.update_billing_period(
            user_email, current_period_start, current_period_end
        )
    elif event_type == "invoice.paid":
        subscription_id = event.data.object.get("subscription")
        if not subscription_id:
            return  # Invoice isn't for a subscription
        subscription = stripe.Subscription.retrieve(subscription_id)
        next_period_start = datetime.fromtimestamp(subscription.current_period_start)
        next_period_end = datetime.fromtimestamp(subscription.current_period_end)
        customer_id = subscription.get("customer")
        customer = stripe.Customer.retrieve(customer_id)
        user_email = customer.email

        stripe_handler.update_billing_period(
            user_email, next_period_start, next_period_end
        )
    elif event_type == "customer.subscription.deleted":
        customer_id = event.data.object["customer"]
        stripe_handler.downgrade_user(customer_id)
    else:
        logger.info(f"unhandled event: {event_type}")

    return {"status": "success"}


@router.post("/create-checkout")
async def create_checkout_session(user: CurrentUser):
    # TODO: store customer id in database
    customers = stripe.Customer.list(email=user.email, limit=1)
    if customers.data:
        customer = customers.data[0]
    else:
        customer = stripe.Customer.create(email=user.email)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": config.Config.Constants.STRIPE_SUBSCRIPTION_PRICE_ID,
                    "quantity": 1,
                },
                {
                    "price": config.Config.Constants.STRIPE_USAGE_BASED_PRICE_ID,
                },
            ],
            mode="subscription",
            customer=customer.id,
            success_url=f"{config.Config.Constants.CLIENT_BASE_URL}/return?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.Config.Constants.CLIENT_BASE_URL}/cancel",
        )
        return {"url": checkout_session.url}
    except Exception as e:
        print(e)
        raise HTTPException(400, detail=str(e))
