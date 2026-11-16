from fastapi import APIRouter

from .. import config
from ..models import ai_vendors as models_ai_vendors
from ..schemas import ai_vendors as schemas_ai_vendors

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get(
    "/vendors",
    response_model=schemas_ai_vendors.AIVendorsResponse,
    response_model_exclude_none=True,
)
async def get_vendors() -> schemas_ai_vendors.AIVendorsResponse:
    """List the AI vendors, service tiers, and models enabled for API tasks.

    Returns:
        A successful response whose data is keyed by upper-case vendor name.
        Each vendor contains upper-case tier names and the configured model
        identifiers for that tier. An empty configuration returns empty data.

    Notes:
        The endpoint accepts no path, query, or body inputs. It exposes model
        availability only, never provider credentials or endpoints. Model order
        is not guaranteed. When API-key authentication is enabled, the
        application can reject the request with HTTP 401 before this function
        is called.
    """
    result: dict[str, models_ai_vendors.AIVendorInfo] = {}
    for v in config.settings_llm_vendor.vendors.keys():
        v_name = v.upper()
        result[v_name] = models_ai_vendors.AIVendorInfo(name=v_name, tier_models={})
        for t in config.settings_llm_vendor.vendors[v].keys():
            t_name = t.upper()
            result[v_name].tier_models[t_name] = list(config.settings_llm_vendor.vendors[v][t].models or [])

    return schemas_ai_vendors.AIVendorsResponse(status=200, message="ok", data=result)
