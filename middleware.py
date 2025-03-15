"""
Middleware setup and configuration for the application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from sheetsapi import config


def setup_middleware(app: FastAPI) -> None:
    """
    Configure and add middleware to the FastAPI application.

    Args:
        app: The FastAPI application instance
    """
    # app.add_middleware(
    #     SecureCookiesMiddleware, secrets=[config.Config.Constants.OAUTH_SECRET_TOKEN]
    # )

    # Session middleware for authentication
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.Config.Constants.OAUTH_SECRET_TOKEN,
        same_site="none",
        https_only=True,
        domain="jedwal.co",
    )

    # CORS middleware for cross-origin requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            config.Config.Constants.CLIENT_BASE_URL,
            config.Config.Constants.CLIENT_APP_BASE_URL,
            config.Config.Constants.API_BASE_URL,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
