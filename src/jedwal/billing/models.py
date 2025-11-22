"""Billing domain models."""

from datetime import datetime

from pydantic import BaseModel, Field

from jedwal.account.models import AccountId


class BillingInfo(BaseModel):
    """Billing information stored on account items."""

    account_id: AccountId = Field(..., description="The account we're billing")
    billing_start: datetime | None = None
    billing_end: datetime | None = None
    stripe_subscription_id: str | None = None
    stripe_customer_id: str | None = None


class CheckoutSession(BaseModel):
    """Checkout session response."""

    url: str
