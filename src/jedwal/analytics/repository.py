import time
from datetime import datetime

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.analytics.models import AnalyticsLog, ResourceType


def to_item(*, log: AnalyticsLog) -> dict:
    return {
        "PK": f"ANALYTICS#{log.owner_id}#{log.resource_type}#{log.resource_id}",
        "SK": f"{log.timestamp.isoformat()}#{log.request_id}",
        "owner_id": log.owner_id,
        "resource_id": log.resource_id,
        "resource_type": log.resource_type,
        "status_code": log.status_code,
        "cache_result": log.cache_result,
        "path": log.path,
        "timestamp": log.timestamp.isoformat(),
        "request_id": log.request_id,
    }


def to_analytics_log(*, item: dict) -> AnalyticsLog:
    return AnalyticsLog(
        owner_id=item["owner_id"],
        resource_id=item["resource_id"],
        resource_type=item["resource_type"],
        status_code=item["status_code"],
        cache_result=item["cache_result"],
        path=item["path"],
        timestamp=datetime.fromisoformat(item["timestamp"]),
        request_id=item["request_id"],
    )


def batch_write_logs(*, table: Table, logs: list[AnalyticsLog]) -> dict[str, int]:
    if not logs:
        return {"success": 0, "failures": 0}

    results = {"success": 0, "failures": 0}

    for i in range(0, len(logs), 25):
        batch = logs[i : i + 25]

        with table.batch_writer() as writer:
            for log in batch:
                try:
                    item = to_item(log=log)
                    writer.put_item(Item=item)
                    results["success"] += 1
                except ClientError:
                    results["failures"] += 1

        time.sleep(0.05)

    return results


def get_logs_for_resource(
    *,
    table: Table,
    owner_id: str,
    resource_type: ResourceType,
    resource_id: str,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[AnalyticsLog]:
    # TEMPORARY: Query old format (without resource_type in PK) for backward compatibility
    # TODO: Remove this after migrating all analytics data to new format
    pk_old = f"ANALYTICS#{owner_id}#{resource_id}"

    key_condition = "PK = :pk"
    expr_values = {":pk": pk_old}

    if start_time and end_time:
        key_condition += " AND SK BETWEEN :start_time AND :end_time"
        expr_values[":start_time"] = start_time
        expr_values[":end_time"] = end_time
    elif start_time:
        key_condition += " AND SK >= :start_time"
        expr_values[":start_time"] = start_time
    elif end_time:
        key_condition += " AND SK <= :end_time"
        expr_values[":end_time"] = end_time

    response = table.query(
        KeyConditionExpression=key_condition,
        ExpressionAttributeValues=expr_values,
    )

    items = response.get("Items", [])

    # Adapt old format items to new AnalyticsLog model
    # TODO: update this to use new format once analytics format is updated
    logs = []
    for item in items:
        # Handle old field names and missing fields
        log = AnalyticsLog(
            owner_id=item.get("owner_id", owner_id),
            resource_id=item.get(
                "resource_id", item.get("sheet_api_name", resource_id)
            ),
            resource_type=item.get(
                "resource_type", resource_type
            ),  # Use passed resource_type as fallback
            status_code=item["status_code"],
            cache_result=item["cache_result"],
            path=item["path"],
            timestamp=datetime.fromisoformat(
                item.get("timestamp", item.get("request_time"))
            ),
            request_id=item.get("request_id", "TODO FIX THIS"),  # fix this
        )
        logs.append(log)

    return logs


def delete_logs_for_resource(
    *, table: Table, owner_id: str, resource_type: ResourceType, resource_id: str
) -> dict[str, int]:
    # TEMPORARY: Use old PK format for backward compatibility
    # TODO: Update to new format after migration
    pk = f"ANALYTICS#{owner_id}#{resource_id}"

    # Query all items for this resource
    response = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": pk},
        ProjectionExpression="PK, SK",  # Only fetch keys for deletion
    )

    items = response.get("Items", [])

    if not items:
        return {"deleted": 0}

    # Delete in batches of 25 (DynamoDB batch limit)
    deleted_count = 0

    for i in range(0, len(items), 25):
        batch = items[i : i + 25]

        with table.batch_writer() as writer:
            for item in batch:
                writer.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                deleted_count += 1

        time.sleep(0.05)

    return {"deleted": deleted_count}
