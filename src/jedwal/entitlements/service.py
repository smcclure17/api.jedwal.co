from jedwal.account.models import Account
from jedwal.apis.models import Api
from jedwal.common.exceptions import QuotaExceededException, UnauthorizedException
from jedwal.organizations.membership.models import MemberType
from jedwal.posts.models import Post


def check_can_create_post(*, account: Account, current_count: int):
    """Check if account can create another post."""
    if account.account_status == "free" and current_count >= 2:
        raise QuotaExceededException(
            detail="Free accounts can only have 2 posts. Upgrade to premium for unlimited."
        )


def check_can_create_api(*, account: Account, current_count: int):
    """Check if account can create another API."""
    if account.account_status == "free" and current_count >= 2:
        raise QuotaExceededException(
            detail="Free accounts can only have 2 APIs. Upgrade to premium for unlimited."
        )


def check_can_create_organization(*, account: Account):
    """Check if account can create organization."""
    if account.account_status == "free":
        raise QuotaExceededException(
            detail="Free accounts cannot create organizations. Upgrade to premium."
        )


def check_can_delete_organization(*, member_status: MemberType):
    if member_status != "owner":
        raise UnauthorizedException(
            detail=f"Only owners can delete organization. Account has member status {member_status}."
        )


def check_can_access_post(*, post: Post):
    """Check if frozen post can be accessed."""
    if post.frozen:
        raise QuotaExceededException(
            detail="Post is frozen. Re-upgrade to premium to unfreeze."
        )


def check_can_access_api(*, api: Api):
    """Check if frozen post can be accessed."""
    if api.frozen:
        raise QuotaExceededException(
            detail="API is frozen. Re-upgrade to premium to unfreeze."
        )
