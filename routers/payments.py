"""
Payment processing routes and webhook handlers.
"""

import logging
import stripe
from fastapi import APIRouter, Header, HTTPException
from starlette.requests import Request

from dependencies import CurrentUser
from sheetsapi import config, sheet_api_repo_v2, stripe_helpers

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
    try:
        event = stripe_helpers.get_event(payload=data, header=stripe_signature)
    except stripe.SignatureVerificationError as error:
        raise HTTPException(400, detail=str(error))

    event_type = event["type"]
    if event_type == "checkout.session.completed":
        user_email = event.data.object["customer_details"]["email"]
        stripe_helpers.upgrade_user(user_email)
    elif event_type == "customer.subscription.deleted":
        customer_id = event.data.object["customer"]
        stripe_helpers.downgrade_user(customer_id)
    elif event_type == "customer.subscription.updated":
        subscription = event.data.object
        status = subscription.get("status")
        customer_id = subscription.get("customer")
        customer = stripe.Customer.retrieve(customer_id)
        customer_email = customer.email

        if status == "past_due":
            stripe_helpers.send_past_due_warning_email(customer_id)
        elif status == "active":
            stripe_helpers.upgrade_user(customer_email)
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


@router.get("/success")
async def checkout_success(session_id: str):
    try:
        # Retrieve the session to verify it was successful
        session = stripe.checkout.Session.retrieve(session_id)

        customer_id = session.customer
        subscription_id = session.subscription

        email = session.customer_details.email
        stripe_helpers.upgrade_user(email, customer_id, subscription_id)

        return {"status": "success", "message": "Subscription activated!"}
    except Exception as e:
        raise HTTPException(400, detail=str(e))
