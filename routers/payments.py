"""
Payment processing routes and webhook handlers.
"""
import logging
import stripe
from fastapi import APIRouter, Header, HTTPException
from starlette.requests import Request

from sheetsapi import sheet_api_manager, stripe_helpers

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])
api_manager = sheet_api_manager.SheetManager()


@router.post("/stripe-webhook")
async def webhook_received(
    request: Request, stripe_signature: str = Header(None)
):
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
        stripe_helpers.upgrade_user(user_email, api_manager)
    elif event_type == "customer.subscription.deleted":
        customer_id = event.data.object["customer"]
        stripe_helpers.downgrade_user(customer_id, api_manager)
    else:
        logger.info(f"unhandled event: {event_type}")

    return {"status": "success"}