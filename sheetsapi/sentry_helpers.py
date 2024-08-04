import logging
import sentry_sdk
from sheetsapi import config


logger = logging.getLogger(__name__)


def init():
    """Initialize Sentry SDK."""
    logger.info("Initializing Sentry SDK")
    sentry_sdk.init(
        config.Config.Constants.SENTRY_DSN,
        traces_sample_rate=1.0,
        environment=config.Config.Constants.ENVIRONMENT,
    )
