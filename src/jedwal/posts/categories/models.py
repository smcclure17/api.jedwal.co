"""Category models for posts."""

from pydantic import Field

from jedwal.account.models import AccountId
from jedwal.common.schemas import BaseSchema
from jedwal.posts.models import PostKey


class CategoryPostRelationship(BaseSchema):
    """Bidirectional relationship between a category and a post.

    Stored as two items in DynamoDB using adjacency list pattern:
    1. Category -> Post: PK=CATEGORY#{owner_id}#{category}, SK=POST#{post_key}
    2. Post -> Category: PK=POST#{owner_id}#{post_key}, SK=CATEGORY#{category}
    """

    owner_id: AccountId = Field(..., description="Owner account ID")
    post_key: PostKey = Field(..., description="Post key")
    category: str = Field(..., description="Category name")
    relationship_type: str = Field(
        ..., description="Either 'category_to_post' or 'post_to_category'"
    )


class CategoryCreate(BaseSchema):
    """Schema for adding a category to a post."""

    category: str = Field(..., description="Category name to add")


class CategoryRead(BaseSchema):
    """Schema for returning category information."""

    category: str = Field(..., description="Category name")
