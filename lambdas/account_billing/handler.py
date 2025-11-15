"""Lambda handler to report API usage to Stripe usage meters for billing."""

import logging
import os
import uuid
from datetime import datetime, timedelta

import boto3
import stripe

from jedwal.account.service import get_account
from jedwal.analytics.service import stream_api_logs_for_account
from jedwal.billing.models import BillingInfo
from jedwal.billing.repository import get_accounts_by_billing_end_date
from jedwal.common import sentry
from jedwal.config import settings
from jedwal.database.core import get_table
from jedwal.organizations.service import get_organization

IS_LAMBDA = os.getenv("LAMBDA_TASK_ROOT")
if IS_LAMBDA:
    sentry.init()

stripe.api_key = settings.stripe_secret_key

logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
table = get_table()


def handler(event, _context):
    billing_cycle_end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    users_to_report = get_accounts_by_billing_end_date(
        table=table, billing_end_date=billing_cycle_end_date
    )

    for user in users_to_report:
        account_id = user.account_id
        end_date = user.billing_end
        start_date = user.billing_start
        email = _get_billing_account_email(user)
        customer = _get_account_stripe_customer(email=email)

        usage = calculate_usage_cost(account_id, start_date, end_date)
        report_usage_to_stripe(customer.id, usage["billable_requests"])
        print(f"Reported {usage['billable_requests']} requests for email {email}")


def calculate_usage_cost(
    billing_account_id: str,
    start: str,
    end: str,
):
    """Calculate usage cost without loading all records into memory"""

    total_requests = 0
    for request in stream_api_logs_for_account(
        table=table, owner_id=billing_account_id, start_time=start, end_time=end
    ):
        # We only charge on data refreshes (cache misses)
        if request.cache_result == "MISS":
            total_requests += 1

    billable_requests = max(0, total_requests - settings.free_tier_request_limit)

    return {"total_requests": total_requests, "billable_requests": billable_requests}


def report_usage_to_stripe(stripe_customer_id, usage_quantity):
    """Report usage to Stripe for a specific metered subscription"""
    identifier = (
        f"{stripe_customer_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4()}"
    )

    stripe.billing.MeterEvent.create(
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


# This is not ideal, but i don't want to include too much in the billing info
# domain, so for now we just check if we're working with an organization,
# and if so, grab the orgs billing account.
def _get_billing_account_email(info: BillingInfo):
    org = get_organization(table=table, organization_id=info.account_id)
    if org is not None:
        account = get_account(table=table, id=org.billing_account_id)
    else:
        account = get_account(table=table, id=info.account_id)
    return account.email
