from datetime import datetime, timedelta, timezone
import time
from typing import Callable, Optional, Tuple
import boto3
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from sheetsapi.account_repo import AccountRepo
from sheetsapi.config import Config


# TODO: find a better, more centralized location for this
# Rate limit levels for each account type
# 167 requests per day enforces the 5k free refreshes per month (167 * 30 = ~5k)
# Premium rate limit is just a high number to make sure we're not getting hit hard.
API_RATE_LIMIT_VALUES = {"free": 167, "premium": 1_000_000}
RATE_LIMIT_WINDOW_SECONDS = 86400  # one day


class RateLimitExceededError(Exception):
    """Rate limit exceeded"""

    def __init__(self, resource_type, resource_id, limit, reset_time):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.limit = limit
        self.reset_time = reset_time
        super().__init__(
            f"Rate limit exceeded for {resource_type}:{resource_id}. Limit: {limit}"
        )


class RateLimitRepo:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name

    @property
    def table(self):
        return self.client.Table(self.table_name)

    @classmethod
    def from_table_name(cls, table_name: str = Config.Constants.SHEETS_API_TABLE):
        client = boto3.resource("dynamodb", region_name=Config.Constants.AWS_REGION)
        return RateLimitRepo(client, table_name)

    def check_rate_limit(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 167,  # 167 * 30 = ~5k monthly requests
        window_seconds: int = 86400,  # one day
    ) -> Tuple[bool, int]:
        """Check if a resource has exceeded its rate limit

        Args:
            resource_type: Type of resource (IP, API, USER, etc.)
            resource_id: ID of the resource (IP address, API ID, user ID)
            limit: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds (default: 86400 seconds = 1 day)

        Returns:
            Tuple[bool, int]: (has_exceeded_limit, current_count)

        Raises:
            RateLimitExceededError: If rate limit is exceeded
        """
        now = datetime.now(timezone.utc)
        # Create a timestamp for today: YYYY-MM-DD
        timestamp_day = now.strftime("%Y-%m-%d")

        # Format for finding our rate limit record
        pk = f"RATE#{resource_type}#{resource_id}"
        sk = timestamp_day

        try:
            # Try to update an existing count, or create if not exists
            response = self.table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression="ADD #count :increment SET expiresAt = :expires_at",
                ExpressionAttributeNames={"#count": "count"},
                ExpressionAttributeValues={
                    ":increment": 1,
                    ":expires_at": int(time.time())
                    + window_seconds
                    + 300,  # Add buffer
                },
                ReturnValues="UPDATED_NEW",
            )

            # Get the updated count
            current_count = response.get("Attributes", {}).get("count", 1)

            # Check if over limit
            if current_count > limit:
                # Calculate when the rate limit resets - next day at midnight UTC
                tomorrow = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                reset_time = tomorrow.isoformat()
                raise RateLimitExceededError(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    limit=limit,
                    reset_time=reset_time,
                )

            return False, current_count

        except Exception as e:
            # Handle other errors (like throttling, connection issues, etc.)
            if not isinstance(e, RateLimitExceededError):
                sentry_sdk.capture_exception(e)
                # If we fail, default to allowing the request
                return False, 0
            else:
                raise

    def get_rate_limit_counts(
        self, resource_type: str, resource_id: str, days: int = 1
    ) -> dict[str, int]:
        """Get rate limit counts for a resource over multiple days

        Args:
            resource_type: Type of resource (IP, API, USER, etc.)
            resource_id: ID of the resource (IP address, API ID, user ID)
            days: Number of days to retrieve (default: 5)

        Returns:
            Dict[str, int]: Dictionary mapping day timestamps to request counts
        """
        now = datetime.now(timezone.utc)
        counts = {}

        # Query for the last 'days' worth of rate limit records
        try:
            response = self.table.query(
                KeyConditionExpression="#pk = :pk AND #sk > :min_time",
                ExpressionAttributeNames={"#pk": "PK", "#sk": "SK"},
                ExpressionAttributeValues={
                    ":pk": f"RATE#{resource_type}#{resource_id}",
                    ":min_time": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
                },
            )

            items = response.get("Items", [])
            for item in items:
                counts[item["SK"]] = item.get("count", 0)

            return counts

        except Exception as e:
            sentry_sdk.capture_exception(e)
            return {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting specifically to API and doc routes (/api/, /doc/)"""

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: Optional[RateLimitRepo] = None,
        account_repo: Optional[AccountRepo] = None,
    ):
        super().__init__(app)
        self.api_repo = rate_limiter or RateLimitRepo.from_table_name()
        self.account_repo = account_repo or AccountRepo.from_table_name()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not (path.startswith("/api/") or path.startswith("/doc/")):
            return await call_next(request)
        elif "category" in path:
            return await call_next(request)  # hack for category routes

        path_parts = request.url.path.split("/")
        if len(path_parts) >= 4:  # /{api or doc}/{owner_id}/{sheet_api_name}
            owner_id = path_parts[2]

            account = self.account_repo.get_account(owner_id)
            print(account, "ACCOUNT")
            account_status = account["account_status"]
            api_rate_limit = API_RATE_LIMIT_VALUES[account_status]

            try:
                self.api_repo.check_rate_limit(
                    resource_type="API",
                    resource_id=owner_id,
                    limit=api_rate_limit,
                    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
                )
            except RateLimitExceededError as e:
                message = {
                    "free": "Try increasing the Update Cadence of your APIs, or upgrade to Pro.",
                    "premium": "This is a soft/hidden rate limit. Reach out to hello@jedwal.co to have this lifted",
                }
                return JSONResponse(
                    content=(
                        f"API rate limit exceeded. "
                        f"Limit of {api_rate_limit} refreshes per day on {account_status} plan. "
                        f"Try again after {e.reset_time}Z. "
                        f"{message[account_status]}"
                    ),
                    status_code=429,
                    headers={
                        "Retry-After": f"{RATE_LIMIT_WINDOW_SECONDS}",
                        "X-RateLimit-Limit": str(e.limit),
                        "X-RateLimit-Reset": e.reset_time,
                    },
                )

        response = await call_next(request)
        return response
