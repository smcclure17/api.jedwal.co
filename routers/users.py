"""
User-related routes and operations.
"""

from fastapi import APIRouter

from sheetsapi import user_helpers
from sheetsapi.models.api_models import UserDataResponse
from dependencies import CurrentUser

router = APIRouter(tags=["users"])


@router.get("/get-user-data", response_model=UserDataResponse)
async def get_user_data(user: CurrentUser):
    """
    Get information about the currently authenticated user.

    Returns:
        UserDataResponse: User profile and account information
    """
    user_fields = user_helpers.fetch_fields_for_user(
        user.email, fields=["apiCount", "premium", "userId"]
    )

    if user_fields is None:
        raise ValueError(f"No fields found for user {user.email}")

    return UserDataResponse(
        id=user_fields.userId,
        email=user.email,
        name=user.name,
        api_count=user_fields.apiCount,
        premium=user_fields.premium,
    )
