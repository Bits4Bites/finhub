from fastapi import APIRouter, HTTPException, Path, Response

from .. import config

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


@router.get("/index/{index_id}", response_class=Response)
def get_market_index(
    index_id: str = Path(
        description=(
            "The market index ID to retrieve. Allowed values: ASX20, ASX50, ASX100, ASX200, ASX300, "
            "HNX30, NASDAQ100, SP400, SP500, SP600, VN30, VN100."
        )
    ),
) -> Response:
    """
    Return the preloaded static JSON file for a supported market index.

    The index ID is case-insensitive and restricted to ``SUPPORTED_INDEX_IDS``.
    Raises HTTP 404 when the ID is unsupported or its content is not cached.
    """
    normalized_index_id = index_id.upper()
    if normalized_index_id not in SUPPORTED_INDEX_IDS:
        raise HTTPException(status_code=404, detail="Market index not found")

    raw_json = config.market_indices.raw_json.get(normalized_index_id)
    if raw_json is None:
        raise HTTPException(status_code=404, detail="Market index not found")

    return Response(content=raw_json, media_type="application/json")
