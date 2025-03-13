"""
Shared dependencies used across the application.
"""

import logging
from typing import Annotated

import fastapi
from fastapi import Depends
from starlette.requests import Request

from sheetsapi.models.domain_models import UserSession

logger = logging.getLogger(__name__)


def get_current_user(request: Request) -> UserSession:
    """Authentication middleware/dependency"""
    user = request.session.get("user")

    if user is None:
        raise fastapi.HTTPException(status_code=401, detail="Not authenticated")

    # TEMP: get access_token from session the old way
    if "access_token" not in user:
        user["access_token"] = request.session.get("access_token")

    return UserSession(**user)


CurrentUser = Annotated[UserSession, Depends(get_current_user)]
