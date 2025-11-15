import logging

import sentry_sdk
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

from jedwal.config import settings

logger = logging.getLogger(__name__)


def init():
    """Initialize Sentry SDK."""
    logger.info("Initializing Sentry SDK")
    sentry_sdk.init(
        settings.sentry_dsn,
        integrations=[AwsLambdaIntegration()],
        traces_sample_rate=1.0,
        environment=settings.environment,
    )
