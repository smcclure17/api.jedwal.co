import boto3
from datetime import datetime
import logging

from sheetsapi import config

logger = logging.getLogger(__name__)


def create_cloudfront_client():
    if config.Config.Constants.ENVIRONMENT == "local":
        logger.info("Local env detected. Not initializing Cloudfront")
        return
    return boto3.client("cloudfront")


def invalidate_cache(cloudfront, distribution_id, path):
    caller_reference = f"invalidation-{datetime.now().isoformat()}"

    # Specify the invalidation request parameters
    invalidation = cloudfront.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {
                "Quantity": 1,
                "Items": [path],  # Path of the deleted page, e.g., '/my-page'
            },
            "CallerReference": caller_reference,
        },
    )
    return invalidation
