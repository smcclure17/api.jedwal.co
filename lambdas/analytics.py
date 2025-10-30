"""Lambda handler to read logs from S3 and write to DynamoDB"""

import logging
import gzip
import os

import boto3
from sheetsapi import config

config.Config.init()

from sheetsapi import sentry_helpers
from sheetsapi.analytics_client import AnalyticsClient

logger = logging.getLogger(__name__)

IS_LAMBDA = os.getenv("LAMBDA_TASK_ROOT")
if IS_LAMBDA:
    sentry_helpers.init()

analytics_client = AnalyticsClient.from_table_name()
s3 = boto3.client("s3")


def handler(event, _context):
    """Extract CloudFront logs from S3 and write to DynamoDB

    Processes resource requests (calls to /api/* and /doc/* paths)
    for analytics tracking.
    """

    results = []
    for record in event["Records"]:
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = record["s3"]["object"]["key"]

        try:
            response = s3.get_object(Bucket=bucket_name, Key=object_key)
            with gzip.GzipFile(fileobj=response["Body"]) as gz:
                object_content = gz.read().decode("utf-8")
        except Exception as e:
            logger.error(
                f"Error getting object {object_key} from bucket {bucket_name}. Error: {str(e)}"
            )
            raise e

        log_lines = parse_cloudfront_log_lines(object_content)
        prepped_rows = []
        for line in log_lines:
            stem = line["cs-uri-stem"]

            # Extract endpoint type (api or doc)
            if "/api/" in stem:
                resource_type = "api"
                prefix = "/api/"
            elif "/doc/" in stem:
                resource_type = "doc"
                prefix = "/doc/"
            else:
                continue  # Skip non-resource requests

            request_id = line["x-edge-request-id"]
            path = stem.split(prefix)[1]
            parts = path.split("/")

            if len(parts) < 2:
                continue  # Skip malformed requests

            owner_id = parts[0]
            resource_name = parts[1]
            sheet_analytics_id = f"ANALYTICS#{owner_id}#{resource_name}"
            timestamp = f"{line['date']}T{line['time']}Z"

            prepped_rows.append(
                {
                    "PK": sheet_analytics_id,
                    "SK": timestamp,
                    "status_code": int(line["sc-status"]),
                    "account_id": owner_id,
                    "sheet_api_name": resource_name,
                    "resource_type": resource_type,
                    "path": path,
                    "timestamp": timestamp,
                    "request_id": request_id,
                    "cache_result": line["x-edge-result-type"],
                }
            )

    results.append(analytics_client.batch_write_api_logs(prepped_rows))
    return {
        "statusCode": 200,
        "results": results,
    }


def parse_cloudfront_log_lines(content: str) -> list[dict]:
    """Parse CloudFront log lines text into a list of dictionaries

    CloudFront log format is:
    ```txt
    #Version: 1.0
    #Fields: field1    field2    field3
    value1    value2    value3
    ```
    """
    lines = content.strip().split("\n")

    # Extract the version and fields information
    fields_line = lines[1]
    field_names = fields_line.split(": ")[1].split()

    log_entries = []
    for line in lines[2:]:
        field_values = line.split("\t")
        log_entry = {}
        for name, value in zip(field_names, field_values):
            log_entry[name] = value
        log_entries.append(log_entry)
    return log_entries
