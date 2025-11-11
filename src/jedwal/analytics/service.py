from jedwal.analytics import repository
from jedwal.analytics.models import AnalyticsLog, ResourceType
from jedwal.database.core import DbTable


def batch_write_logs(*, table: DbTable, logs: list[AnalyticsLog]) -> dict[str, int]:
    return repository.batch_write_logs(table=table, logs=logs)


def get_logs_for_resource(
    *,
    table: DbTable,
    owner_id: str,
    resource_type: ResourceType,
    resource_id: str,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[AnalyticsLog]:
    return repository.get_logs_for_resource(
        table=table,
        owner_id=owner_id,
        resource_type=resource_type,
        resource_id=resource_id,
        start_time=start_time,
        end_time=end_time,
    )
