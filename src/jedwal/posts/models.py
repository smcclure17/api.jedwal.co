from typing import Annotated, Any

from pydantic import Field

from jedwal.account.models import AccountId, RefreshTokenInfo
from jedwal.common.schemas import BaseSchema, TimestampMixin

PostKey = Annotated[
    str,
    Field(
        pattern=r"^[a-zA-Z0-9-]+$",
        description="The name/ID/slug of the post (alphanumeric and hyphens only)",
        min_length=3,
        max_length=50,
    ),
]


class PostBase(BaseSchema, TimestampMixin):
    """"""


class PostCreateRequest(BaseSchema):
    post_key: PostKey
    google_doc_id: str = Field(
        ..., description="The Google Doc ID to create a post from"
    )


class PostCreateRead(BaseSchema):
    post_key: PostKey = Field(..., description="Post ID of the newly created post.")


class PostCreate(BaseSchema):
    owner_id: AccountId = Field(
        ..., description="The post owner (organization or account ID)"
    )
    post_key: PostKey
    google_doc_id: str = Field(
        ..., description="The Google Doc ID to create a post from"
    )
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token for accessing the sheet"
    )


class Post(PostBase):
    post_key: PostKey
    owner_id: AccountId
    google_doc_id: str
    google_doc_payload: str
    google_doc_ast: str
    title: str
    creator: str
    refresh_token_info: RefreshTokenInfo = Field(
        ..., description="OAuth refresh token for accessing the sheet"
    )
    frozen: bool = Field(default=False, description="Whether post is frozen/disabled")
    categories: list[str] | None = Field(
        default=None, description="Post categories (Denormalized)"
    )


class PostRead(PostBase):
    post_key: PostKey
    owner_id: AccountId
    title: str
    google_doc_id: str
    categories: list[str] | None = Field(default=None, description="Post categories")


class PostDocumentDataRead(PostBase):
    title: str
    document_id: str
    frontmatter: dict[str, Any] | None = Field(
        default=None, description="Frontmatter YAML fields."
    )
    content: str = Field(..., description="The post data content.")
