from ..models import ai as ai_models
from ..models import finhub as models
from ..services import ai as ai_services
from .base_req_resp import BaseRequest, BaseResponse


class AIVendorsResponse(BaseResponse):
    """
    Response schema, containing the list of available AI vendors and enabled API tiers and models.

    Attributes:
        data (dict[str, ai_models.AIVendorInfo]): A dictionary where the key is the vendor name, and the value is an object containing the vendor information, including supported API tiers and models.
    """

    data: dict[str, ai_models.AIVendorInfo] = {}


# ----------------------------------------------------------------------#


class AnalyzeDividendEventResponse(BaseResponse):
    """
    Response schema, containing the analysis result of a dividend event.

    Attributes:
        data (models.DividendEventAnalysis): An object containing the analysis result of the dividend event.
    """

    data: models.DividendEventAnalysis | None = None


# ----------------------------------------------------------------------#


class AnalyzePortfolioRequest(BaseRequest):
    """
    Request to analyze a portfolio.

    Attributes:
        current_allocation (list[models.HoldingTicker]): A list of current holding tickers in the portfolio.
        country (str): The country code of the portfolio (e.g. AU for Australia).
        investor_theme (str): (optional) The investor's theme/style, e.g. '- Risk tolerance: moderate\n- Time horizon: 5-10 years\n- Goal: capital growth\n- Rebalance frequency: semi-annual'.
    """

    current_allocation: list[models.HoldingTicker] = []
    country: str = ""
    investor_theme: str = ai_services.DEFAULT_INVESTOR_THEME


class AnalyzePortfolioResponse(BaseResponse):
    """
    Response schema, containing the analysis result of a portfolio request.

    Attributes:
        data (models.PortfolioAnalysis): The analysis result of the portfolio request.
    """

    data: models.PortfolioAnalysis | None = None
