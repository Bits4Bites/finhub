from pydantic import Field

from ..models import ai_vendors as models_ai_vendors
from .base_req_resp import BaseResponse


class AIVendorsResponse(BaseResponse[dict[str, models_ai_vendors.AIVendorInfo]]):
    """Response envelope containing enabled AI vendors, tiers, and models."""

    data: dict[str, models_ai_vendors.AIVendorInfo] = Field(
        default={},
        description="Enabled AI vendors keyed by vendor identifier.",
    )
