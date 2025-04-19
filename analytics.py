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

    Only processes API requests (calls to /api/* paths) since
    these are the APIs we want analytics on.
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
            if "/api/" not in line["cs-uri-stem"]:
                continue  # Only care about API requests, not user data

            request_id = line["x-edge-request-id"]
            # api log lines are formatted /api/{account_id}/{sheet_id}
            parts: list[str] = line["cs-uri-stem"].split("/api/")[1].split("/")
            owner_id = parts[0]
            sheet_api_name = parts[1]
            sheet_analytics_id = f"ANALYTICS#{owner_id}#{sheet_api_name}"
            timestamp = f"{line['date']}T{line['time']}Z"

            prepped_rows.append(
                {
                    "PK": sheet_analytics_id,
                    "SK": timestamp,
                    "status_code": int(line["sc-status"]),
                    "account_id": owner_id,
                    "sheet_api_name": sheet_api_name,
                    "path": line["cs-uri-stem"].split("/api/")[1],
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
