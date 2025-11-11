from datetime import datetime
from typing import Literal

from pydantic import Field

from jedwal.common.schemas import BaseSchema

ResourceType = Literal["api", "post"]


class AnalyticsLog(BaseSchema):
    owner_id: str = Field(
        ..., description="Account or organization ID that owns the resource"
    )
    resource_id: str = Field(..., description="API key or post key")
    resource_type: ResourceType = Field(..., description="Type of resource")
    status_code: int = Field(..., description="HTTP status code")
    cache_result: str = Field(
        ..., description="CloudFront cache result (Hit, Miss, etc.)"
    )
    path: str = Field(..., description="Full request path")
    timestamp: datetime = Field(..., description="Request timestamp")
    request_id: str = Field(..., description="Unique request identifier")


class AnalyticsLogRead(BaseSchema):
    owner_id: str
    resource_id: str
    resource_type: ResourceType
    status_code: int
    cache_result: str
    path: str
    timestamp: datetime
    request_id: str
