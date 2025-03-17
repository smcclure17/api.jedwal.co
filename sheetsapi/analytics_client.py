from typing import List, Dict, Any, Optional
import time

import boto3
from boto3.resources.base import ServiceResource
from botocore.exceptions import ClientError
import sentry_sdk

from sheetsapi import config


class AnalyticsClient:
    """Client for handling API analytics operations like storing and querying request logs."""

    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name

    @property
    def table(self) -> ServiceResource:
        return self.client.Table(self.table_name)

    @classmethod
    def from_table_name(
        cls, table_name: str = config.Config.Constants.SHEETS_API_TABLE
    ):
        client = boto3.resource(
            "dynamodb", region_name=config.Config.Constants.AWS_REGION
        )
        return AnalyticsClient(client, table_name)

    def batch_write_api_logs(self, logs: List[Dict[str, Any]]):
        """Batch write API logs into the database"""
        if not logs:
            return {"success": 0, "failures": 0}

        # Process logs in batches of 25 (DynamoDB's limit for batch operations)
        results = {"success": 0, "failures": 0}
        for i in range(0, len(logs), 25):
            batch = logs[i : i + 25]
            write_requests = []

            for log in batch:
                analytics_id = f"ANALYTICS#{log['account_id']}#{log['sheet_api_name']}"
                sort_key = f"{log['timestamp']}#{log['request_id']}"
                item = {
                    "PK": analytics_id,
                    "SK": sort_key,
                    "status_code": log["status_code"],
                    "account_id": log["account_id"],
                    "sheet_api_name": log["sheet_api_name"],
                    "path": log["path"],
                    "request_time": log["timestamp"],
                }

                write_requests.append({"PutRequest": {"Item": item}})

            if write_requests:
                try:
                    self.client.meta.client.batch_write_item(
                        RequestItems={self.table_name: write_requests}
                    )
                    results["success"] += len(write_requests)
                except ClientError as error:
                    sentry_sdk.capture_exception(error)
                    results["failures"] += len(write_requests)

                # Slight delay to avoid hitting rate limits
                time.sleep(0.05)
        return results

    def get_api_logs(
        self, owner_id: str, sheet_api_name: str, start_time: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get API request logs for a specific sheet API."""
        analytics_id = f"ANALYTICS#{owner_id}#{sheet_api_name}"

        if start_time:
            # Query with time filter
            response = self.table.query(
                KeyConditionExpression="PK = :pk AND SK >= :start_time",
                ExpressionAttributeValues={
                    ":pk": analytics_id,
                    ":start_time": start_time,
                },
            )
        else:
            # Query all logs for this sheet API
            response = self.table.query(
                KeyConditionExpression="PK = :pk",
                ExpressionAttributeValues={":pk": analytics_id},
            )

        return response.get("Items", [])

    def get_api_total_invocations(self, owner_id: str, sheet_api_name: str) -> int:
        """
        Get the total number of invocations for an API.

        Args:
            owner_id: The ID of the sheet owner (user or organization)
            sheet_api_name: The name of the sheet API

        Returns:
            Count of total invocations
        """
        analytics_id = f"ANALYTICS#{owner_id}#{sheet_api_name}"

        response = self.table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": analytics_id},
            Select="COUNT",
        )

        return response.get("Count", 0)
