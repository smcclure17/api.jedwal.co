from sheetsapi import dynamodb_client, config


class AnalyticsClient:
    repository: dynamodb_client.DynamoDBClient

    def __init__(self, repository: dynamodb_client.DynamoDBClient = None):
        self.repository = repository or dynamodb_client.DynamoDBClient()

    def get_api_logs(self, path: str, start_time: str) -> list[dict]:
        """Get the total number of invocations for an API path."""
        result = self.repository._generic_query(
            config.Config.Constants.ANALYTICS_TABLE,
            {
                "KeyConditionExpression": "#path = :path_value AND #timestamp > :timestamp_value",
                "ExpressionAttributeNames": {
                    "#path": "path",
                    "#timestamp": "timestamp",
                },
                "ExpressionAttributeValues": {
                    ":path_value": path,
                    ":timestamp_value": start_time,
                },
            },
        )
        return result

    def get_api_total_invocations(self, path: str) -> int:
        """Get the total number of invocations for an API path."""
        result = self.repository.query_index(
            config.Config.Constants.ANALYTICS_TABLE,
            None,  # No index, TODO: make this function's API better (e.g. pass dict of params)
            "path",
            path,
        )
        return len(result)
