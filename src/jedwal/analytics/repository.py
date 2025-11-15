import time
from datetime import datetime
from typing import Any, Iterator, Optional

from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from jedwal.analytics.models import AnalyticsLog, ResourceType


def to_item(*, log: AnalyticsLog) -> dict:
    sk = f"{log.timestamp.isoformat()}#{log.request_id}"
    return {
        "PK": f"ANALYTICS#{log.owner_id}#{log.resource_type}#{log.resource_id}",
        "SK": sk,
        "GSI1PK": f"ANALYTICS#{log.owner_id}",
        "GSI1SK": sk,  # Same as SK for time-based sorting
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
    pk = f"ANALYTICS#{owner_id}#{resource_type}#{resource_id}"

    key_condition = "PK = :pk"
    expr_values = {":pk": pk}

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

    logs = []
    for item in items:
        logs.append(to_analytics_log(item=item))

    return logs


def delete_logs_for_resource(
    *, table: Table, owner_id: str, resource_type: ResourceType, resource_id: str
) -> dict[str, int]:
    pk = f"ANALYTICS#{owner_id}#{resource_type}#{resource_id}"

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


def stream_api_logs_for_account(
    *,
    table: Table,
    owner_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    """
    Stream API request logs for an account using a generator.

    Args:
        owner_id: The account/user ID
        start_time: Optional start timestamp (ISO 8601)
        end_time: Optional end timestamp (ISO 8601)

    Yields:
        Individual analytics records one at a time
    """
    gsi_pk = f"ANALYTICS#{owner_id}"
    key_condition = "GSI1PK = :gsi_pk"
    expr_values = {":gsi_pk": gsi_pk}

    if start_time and end_time:
        key_condition += " AND GSI1SK BETWEEN :start AND :end"
        expr_values[":start"] = start_time
        expr_values[":end"] = end_time
    elif start_time:
        key_condition += " AND GSI1SK >= :start"
        expr_values[":start"] = start_time
    elif end_time:
        key_condition += " AND GSI1SK <= :end"
        expr_values[":end"] = end_time

    # Start with no LastEvaluatedKey
    last_evaluated_key = None

    # Continue querying until we've processed all matching items
    while True:
        # Configure query parameters
        query_params = {
            "IndexName": "GSI1",
            "KeyConditionExpression": key_condition,
            "ExpressionAttributeValues": expr_values,
        }

        # Add LastEvaluatedKey if we have one from a previous query
        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = table.query(**query_params)
        for item in response.get("Items", []):
            yield to_analytics_log(item=item)

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break
