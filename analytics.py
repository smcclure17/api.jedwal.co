"""Lambda handler to read logs from S3 and write to DynamoDB"""

import logging
import gzip

import boto3

from sheetsapi import dynamodb_client, config

logger = logging.getLogger(__name__)
config.Config.init()
db_client = dynamodb_client.DynamoDBClient()
s3 = boto3.client("s3")


def handler(event, _context):
    """Extract CloudFront logs from S3 and write to DynamoDB

    Only processes API requests (calls to /api/* paths) since
    these are the APIs we want analytics on.
    """
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
        lines_processed = 0
        for line in log_lines:
            if "/api/" not in line["cs-uri-stem"]:
                continue  # Only care about API requests, not user data

            line["timestamp"] = f"{line['date']}T{line['time']}Z"
            line_item = {
                "path": line["cs-uri-stem"].split("/api/")[1],  # Table primary key
                "timestamp": line["timestamp"],  # Table range key
                "status_code": int(line["sc-status"]),
            }
            db_client.put_item(config.Config.Constants.ANALYTICS_TABLE, line_item)
            lines_processed += 1
            
    return {
        "statusCode": 200,
        "body": {"message": f"Successfully processed {lines_processed} records"},
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
