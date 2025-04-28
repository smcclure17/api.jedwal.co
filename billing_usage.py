"""Lambda handler to report API usage to Stripe usage meters for billing."""

import uuid
from sheetsapi import config
from sheetsapi.account_repo import AccountRepo

config.Config.init()

from datetime import datetime, timedelta
import logging
import os
from typing import Optional

import boto3
import stripe

from sheetsapi import sentry_helpers
from sheetsapi.analytics_client import AnalyticsClient

stripe.api_key = config.Config.Constants.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)

IS_LAMBDA = os.getenv("LAMBDA_TASK_ROOT")
if IS_LAMBDA:
    sentry_helpers.init()

analytics_client = AnalyticsClient.from_table_name()
account_repo = AccountRepo.from_table_name()
s3 = boto3.client("s3")


def handler(event, _context):
    billing_cycle_end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    users_to_report = account_repo.get_accounts_by_billing_date(billing_cycle_end_date)

    for user in users_to_report:
        account_id = user["account_id"]
        end_date = user["billing_end"]
        start_date = user["billing_start"]
        email = _get_billing_account_email(user)
        customer = _get_account_stripe_customer(email=email)

        usage = calculate_usage_cost(
            account_id, start_date, end_date, client=analytics_client
        )
        report_usage_to_stripe(customer.id, usage["billable_requests"])
        print(f"Reported {usage['billable_requests']} requests for email {email}")


def calculate_usage_cost(
    billing_account_id: str,
    start: str,
    end: str,
    client: Optional[AnalyticsClient] = None,
):
    """Calculate usage cost without loading all records into memory"""

    total_requests = 0
    for request in client.get_api_logs_for_account_streaming(
        billing_account_id, start_time=start, end_time=end
    ):
        # We only charge on data refreshes (cache misses)
        if request.get("cache_result", "") == "MISS":
            total_requests += 1

    billable_requests = max(
        0, total_requests - config.Config.Constants.FREE_TIER_REQUEST_LIMIT
    )

    return {"total_requests": total_requests, "billable_requests": billable_requests}


def report_usage_to_stripe(stripe_customer_id, usage_quantity):
    """Report usage to Stripe for a specific metered subscription"""
    identifier = (
        f"{stripe_customer_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4()}"
    )

    # Create the meter event
    meter_event = stripe.billing.MeterEvent.create(
        event_name="data_refreshes",  # hard-coded from Stripe meter
        payload={"stripe_customer_id": stripe_customer_id, "value": usage_quantity},
        timestamp=int(datetime.now().timestamp()),
        identifier=identifier,
    )


def _get_account_stripe_customer(email: str):
    customers = stripe.Customer.list(email=email, limit=1)
    if not customers.data:
        raise ValueError(f"Stripe customer for email {email} not found")
    return customers.data[0]


def _get_billing_account_email(user: dict):
    if user["type"] == "user":
        return user["email"]
    elif user["type"] == "organization":
        billing_owner = account_repo.get_account(user["billing_account_id"])
        return billing_owner["email"]
