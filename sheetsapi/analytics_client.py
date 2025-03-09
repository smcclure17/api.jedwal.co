from sheetsapi import dynamodb_client, config


class AnalyticsClient:
    repository: dynamodb_client.DynamoDBClient

    def __init__(self, repository: dynamodb_client.DynamoDBClient = None):
        self.repository = repository or dynamodb_client.DynamoDBClient()

    def get_api_logs(self, sheet_api_id: str, start_time: str) -> list[dict]:
        """Get the total number of invocations for an API path."""
        result = self.repository._generic_query(
            config.Config.Constants.ANALYTICS_TABLE,
            {
                "KeyConditionExpression": "#path = :sheet_id AND #timestamp > :timestamp_value",
                "ExpressionAttributeNames": {
                    "#path": "PK",
                    "#timestamp": "timestamp",
                },
                "ExpressionAttributeValues": {
                    ":sheet_id": sheet_api_id,
                    ":timestamp_value": start_time,
                },
            },
        )
        return result

    def get_api_total_invocations(self, sheet_api_id: str) -> int:
        """Get the total number of invocations for an API path."""
        result = self.repository.query_index(
            config.Config.Constants.ANALYTICS_TABLE,
            None,  # No index, TODO: make this function's API better (e.g. pass dict of params)
            "PK",
            sheet_api_id,
        )
        print(result)
        return len(result)
