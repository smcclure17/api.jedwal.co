from fastapi import APIRouter, Query

from jedwal.account.models import AccountId
from jedwal.analytics import service
from jedwal.analytics.models import AnalyticsLogRead, ResourceType
from jedwal.database.core import DbTable

authenticated_analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])


@authenticated_analytics_router.get(
    "/{resource_type}/{resource_id}", response_model=list[AnalyticsLogRead]
)
async def get_resource_analytics(
    account_id: AccountId,
    resource_type: ResourceType,
    resource_id: str,
    table: DbTable,
    start_time: str | None = Query(
        None, description="ISO 8601 timestamp (e.g., 2025-01-01T00:00:00Z)"
    ),
    end_time: str | None = Query(
        None, description="ISO 8601 timestamp (e.g., 2025-01-31T23:59:59Z)"
    ),
):
    """Get analytics logs for a specific API or Post within a time range."""
    logs = service.get_logs_for_resource(
        table=table,
        owner_id=account_id,
        resource_type=resource_type,
        resource_id=resource_id,
        start_time=start_time,
        end_time=end_time,
    )

    return [
        AnalyticsLogRead(
            owner_id=log.owner_id,
            resource_id=log.resource_id,
            resource_type=log.resource_type,
            status_code=log.status_code,
            cache_result=log.cache_result,
            path=log.path,
            timestamp=log.timestamp,
            request_id=log.request_id,
        )
        for log in logs
    ]
