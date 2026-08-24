from fastapi import APIRouter

from .. import config
from ..models import ai as models_ai
from ..schemas import ai as schemas_ai

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get(
    "/vendors",
    response_model=schemas_ai.AIVendorsResponse,
    response_model_exclude_none=True,
)
async def get_vendors() -> schemas_ai.AIVendorsResponse:
    """
    Get the list of available AI vendors and supported API tiers and models.
    """
    result: dict[str, models_ai.AIVendorInfo] = {}
    for v in config.settings_llm_vendor.vendors.keys():
        v_name = v.upper()
        result[v_name] = models_ai.AIVendorInfo(name=v_name, tier_models={})
        for t in config.settings_llm_vendor.vendors[v].keys():
            t_name = t.upper()
            result[v_name].tier_models[t_name] = list(config.settings_llm_vendor.vendors[v][t].models or [])

    return schemas_ai.AIVendorsResponse(status=200, message="ok", data=result)
