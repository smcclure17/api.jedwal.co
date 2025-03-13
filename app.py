"""
Main application entry point.
"""

import logging
import os
import mangum
from fastapi import FastAPI
from sheetsapi import sentry_helpers

from sheetsapi import config

config.Config.init()

# Only start sentry in production
IS_LAMBDA = os.getenv("LAMBDA_TASK_ROOT")
if IS_LAMBDA:
    sentry_helpers.init()

from middleware import setup_middleware
from routers import (
    accounts,
    analytics,
    auth,
    organizations,
    payments,
    sheets,
    ui,
)


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Jedwal.co Sheet API Service",
    description="API for converting Google Sheets to REST endpoints",
    version="1.0.0",
)

# Setup middleware
setup_middleware(app)

# Include all routers
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(sheets.router)
app.include_router(organizations.router)
app.include_router(analytics.router)
app.include_router(payments.router)
app.include_router(ui.router)

# Lambda handler for AWS
handler = mangum.Mangum(app)
