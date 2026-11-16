from fastapi import APIRouter, HTTPException, Path, Response

from ..schemas.base_req_resp import BaseResponse
from ..services import market as services_market

router = APIRouter(prefix="/market", tags=["market"])

SUPPORTED_INDEX_IDS = frozenset(
    {
        "ASX20",
        "ASX50",
        "ASX100",
        "ASX200",
        "ASX300",
        "HNX30",
        "NASDAQ100",
        "SP400",
        "SP500",
        "SP600",
        "VN30",
        "VN100",
    }
)


@router.get(
    "/index/{index_id}",
    response_class=Response,
    responses={
        404: {
            "model": BaseResponse,
            "description": "The index identifier is unsupported or its bundled document is unavailable.",
        }
    },
)
def get_market_index(
    index_id: str = Path(
        description=(
            "The market index ID to retrieve. Allowed values: ASX20, ASX50, ASX100, ASX200, ASX300, "
            "HNX30, NASDAQ100, SP400, SP500, SP600, VN30, VN100."
        )
    ),
) -> Response:
    """Return bundled constituent data for a supported market index.

    Args:
        index_id: Case-insensitive market index identifier from
            ``SUPPORTED_INDEX_IDS``.

    Returns:
        An HTTP 200 response containing the index JSON document verbatim with
        an ``application/json`` content type. The response is raw JSON rather
        than a FinHub response envelope.

    Raises:
        HTTPException: HTTP 404 when the normalized identifier is unsupported
            or no document is available for it.

    Notes:
        The identifier is normalized to uppercase. Unavailable data is treated
        as not found rather than as an empty index.
    """
    normalized_index_id = index_id.upper()
    if normalized_index_id not in SUPPORTED_INDEX_IDS:
        raise HTTPException(status_code=404, detail="Market index not found")

    raw_json = services_market.market_indices.raw_json.get(normalized_index_id)
    if raw_json is None:
        raise HTTPException(status_code=404, detail="Market index not found")

    return Response(content=raw_json, media_type="application/json")
