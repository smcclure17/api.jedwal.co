import logging
import sentry_sdk
from sheetsapi import config
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration


logger = logging.getLogger(__name__)


def init():
    """Initialize Sentry SDK."""
    logger.info("Initializing Sentry SDK")
    sentry_sdk.init(
        config.Config.Constants.SENTRY_DSN,
        integrations=[AwsLambdaIntegration()],
        traces_sample_rate=1.0,
        environment=config.Config.Constants.ENVIRONMENT,
    )
