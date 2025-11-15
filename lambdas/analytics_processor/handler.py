"""Lambda handler to read CloudFront logs from S3 and write to DynamoDB."""

import gzip
import logging
import os
from datetime import datetime

import boto3

from jedwal.analytics import service as analytics_service
from jedwal.analytics.models import AnalyticsLog
from jedwal.common import sentry
from jedwal.database.core import get_table

IS_LAMBDA = os.getenv("LAMBDA_TASK_ROOT")
if IS_LAMBDA:
    sentry.init()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")


def handler(event, context):
    """Extract CloudFront logs from S3 and write to DynamoDB.

    Triggered by: S3 ObjectCreated events for CloudFront log files

    Tracks public-facing resource requests for analytics:
    - /{account_id}/apis/{api_id}
    - /{account_id}/posts/{post_key}

    Ignores management routes (/manage/*) and other non-resource endpoints.

    Args:
        event: S3 event with Records containing bucket and object info
        context: Lambda context (unused)

    Returns:
        Dict with statusCode and processing stats
    """
    table = get_table()
    total_logs_written = 0
    total_logs_failed = 0

    for record in event["Records"]:
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = record["s3"]["object"]["key"]

        logger.info(f"Processing log file: s3://{bucket_name}/{object_key}")

        # Download and decompress CloudFront log file
        try:
            response = s3.get_object(Bucket=bucket_name, Key=object_key)
            with gzip.GzipFile(fileobj=response["Body"]) as gz:
                object_content = gz.read().decode("utf-8")
        except Exception as e:
            logger.error(
                f"Error getting object {object_key} from bucket {bucket_name}: {str(e)}"
            )
            raise

        # Parse CloudFront log format
        log_lines = parse_cloudfront_log_lines(object_content)
        logger.info(f"Parsed {len(log_lines)} log lines from {object_key}")

        # Convert to AnalyticsLog domain models
        analytics_logs = []
        for line in log_lines:
            log = parse_log_line_to_analytics_log(line)
            if log:
                analytics_logs.append(log)

        logger.info(f"Converted {len(analytics_logs)} valid analytics logs")

        # Batch write to DynamoDB using analytics service
        if analytics_logs:
            results = analytics_service.batch_write_logs(
                table=table, logs=analytics_logs
            )
            total_logs_written += results["success"]
            total_logs_failed += results["failures"]

    logger.info(
        f"Analytics processing complete. Written: {total_logs_written}, Failed: {total_logs_failed}"
    )

    return {
        "statusCode": 200,
        "body": {
            "logs_written": total_logs_written,
            "logs_failed": total_logs_failed,
        },
    }


def parse_log_line_to_analytics_log(line: dict) -> AnalyticsLog | None:
    """Parse a CloudFront log line dict into an AnalyticsLog domain model.

    Only processes public-facing resource requests:
    - /{account_id}/apis/{api_id}
    - /{account_id}/posts/{post_key}

    Ignores management routes like /manage/{account_id}/apis/...

    Args:
        line: Parsed CloudFront log line as dict

    Returns:
        AnalyticsLog if the line represents a valid public resource request, None otherwise
    """
    stem = line["cs-uri-stem"]

    # Skip management routes entirely
    if stem.startswith("/manage/"):
        return None

    # Parse public resource routes: /{account_id}/{resource_type}/{resource_id}
    parts = stem.strip("/").split("/")

    # Must have at least 3 parts: account_id, resource_type, resource_id
    if len(parts) < 3:
        return None

    account_id = parts[0]
    resource_type_segment = parts[1]
    resource_id = parts[2]

    # Match only public APIs and posts routes
    if resource_type_segment == "apis":
        resource_type = "api"
    elif resource_type_segment == "posts":
        resource_type = "post"
    else:
        # Not a resource we track (health, auth, billing, etc.)
        return None

    # Parse timestamp
    timestamp_str = f"{line['date']}T{line['time']}Z"
    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

    # Full path for analytics (everything after account_id)
    path = "/".join(parts[1:])

    return AnalyticsLog(
        owner_id=account_id,
        resource_id=resource_id,
        resource_type=resource_type,
        status_code=int(line["sc-status"]),
        cache_result=line["x-edge-result-type"],
        path=path,
        timestamp=timestamp,
        request_id=line["x-edge-request-id"],
    )


def parse_cloudfront_log_lines(content: str) -> list[dict]:
    """Parse CloudFront log file content into a list of log line dicts.

    CloudFront log format is tab-separated with header lines:
    ```
    #Version: 1.0
    #Fields: date time x-edge-location ...
    2025-01-01  12:00:00  ...
    ```

    Args:
        content: Raw CloudFront log file content

    Returns:
        List of dicts, each representing a log line with field names as keys
    """
    lines = content.strip().split("\n")

    if len(lines) < 3:
        logger.warning("CloudFront log file has fewer than 3 lines, skipping")
        return []

    # Extract field names from header (line 1: #Fields: ...)
    fields_line = lines[1]
    if not fields_line.startswith("#Fields:"):
        logger.error("Invalid CloudFront log format, missing #Fields header")
        return []

    field_names = fields_line.split(": ")[1].split()

    # Parse data lines (skip header lines 0 and 1)
    log_entries = []
    for line in lines[2:]:
        if not line.strip() or line.startswith("#"):
            continue  # Skip empty lines and comments

        field_values = line.split("\t")

        if len(field_values) != len(field_names):
            logger.warning(
                f"Skipping malformed log line with {len(field_values)} fields "
                f"(expected {len(field_names)})"
            )
            continue

        log_entry = dict(zip(field_names, field_values, strict=False))
        log_entries.append(log_entry)

    return log_entries
