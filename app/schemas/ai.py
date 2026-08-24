from pydantic import Field

from ..models import ai as models_ai
from .base_req_resp import BaseResponse


class AIVendorsResponse(BaseResponse[dict[str, models_ai.AIVendorInfo]]):
    """Response envelope containing enabled AI vendors, tiers, and models."""

    data: dict[str, models_ai.AIVendorInfo] = Field(
        default={},
        description="Enabled AI vendors keyed by vendor identifier.",
    )
