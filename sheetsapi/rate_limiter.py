from typing import Callable, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from sheetsapi import sheet_api_repo_v2


# TODO: find a better, more centralized location for this
# Rate limit levels for each account type
API_RATE_LIMIT_VALUES = {"free": 20, "premium": 60}


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting specifically to API routes (/api/)"""

    def __init__(
        self,
        app: ASGIApp,
        api_repo: Optional[sheet_api_repo_v2.SheetApiRepo] = None,
    ):
        super().__init__(app)
        self.api_repo = api_repo or sheet_api_repo_v2.SheetApiRepo.from_table_name()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only apply rate limiting to /api/ routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        path_parts = request.url.path.split("/")
        if len(path_parts) >= 4:  # /api/{owner_id}/{sheet_api_name}
            owner_id = path_parts[2]

            account = self.api_repo.get_account(owner_id)
            account_status = account["account_status"]
            api_rate_limit = API_RATE_LIMIT_VALUES[account_status]

            try:
                self.api_repo.check_rate_limit(
                    resource_type="API", resource_id=owner_id, limit=api_rate_limit
                )
            except sheet_api_repo_v2.RateLimitExceededError as e:
                return JSONResponse(
                    content=(
                        f"API rate limit exceeded. "
                        f"Limit of {api_rate_limit} calls per minute on {account_status} plan. "
                        f"Try again after {e.reset_time}Z"
                    ),
                    status_code=429,
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(e.limit),
                        "X-RateLimit-Reset": e.reset_time,
                    },
                )

        response = await call_next(request)
        return response
