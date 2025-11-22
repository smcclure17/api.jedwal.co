from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    Field,
    Json,
    TypeAdapter,
)

from jedwal.account.models import AccountId
from jedwal.common.schemas import BaseSchema
from jedwal.posts.models import PostKey

WebhookType = Literal["GET", "POST"]

# https://github.com/pydantic/pydantic/discussions/6395
# We want URL validation, but pydantic V2 URLs are not strings,
# this is a workaround for now.
http_url_adapter = TypeAdapter(AnyUrl)
Url = Annotated[
    str, BeforeValidator(lambda value: str(http_url_adapter.validate_python(value)))
]


class WebhookBase(BaseSchema):
    url: Url
    method: WebhookType
    name: str | None = None


class Webhook(WebhookBase):
    payload: dict[str, Any] | None = None  # internal models are already dicts


class WebhookCreateRequest(WebhookBase):
    payload: Json[Any] | None = None  # JSON validator for inputs for str --> dict


class WebhookDeleteRequest(WebhookBase):
    pass


class WebhooksRead(BaseSchema):
    account_id: AccountId = Field(..., description="The account owner of the post")
    post_id: PostKey = Field(..., description="The post ID")
    webhooks: list[Webhook] = Field(
        ..., description="The webhook configs for this post"
    )
