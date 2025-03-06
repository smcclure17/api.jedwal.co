"""
Shared dependencies used across the application.
"""

import logging
from typing import Annotated

import fastapi
from fastapi import Depends
from starlette.requests import Request

from sheetsapi import organization_helpers, user_helpers
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


def check_if_org_member(org_id: str, user: UserSession = Depends(get_current_user)):
    """Dependency to ensures the current user is a member of the specified organization."""
    user_fields = user_helpers.fetch_fields_for_user(user.email, ["userId"])
    org = organization_helpers.get_organization(org_id)
    if not org:
        raise fastapi.HTTPException(
            status_code=404, detail=f"Organization with ID {org_id} not found."
        )
    if not organization_helpers.is_organization_member(org_id, user_fields.userId):
        raise fastapi.HTTPException(
            status_code=403, detail="You are not a member of this organization."
        )
    return user_fields.userId


OrgMember = Annotated[str, Depends(check_if_org_member)]
