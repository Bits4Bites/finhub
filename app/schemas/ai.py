from ..models import ai as models_ai
from ..models import event as models_event
from ..models import finhub as models
from ..services import ai as services_ai
from ..services import msai_analyze_ticker as service_analyze_ticker
from .base_req_resp import BaseRequest, BaseResponse


class AnalysisResponse(BaseResponse):
    """
    Response schema, containing the analysis result from an AI model.

    Attributes:
        data (models.AnalysisResponse): An object containing the analysis response of the AI model.
    """

    data: models_ai.AnalysisResult | None = None


# ----------------------------------------------------------------------#


class AnalyzeTickerRequest(BaseRequest):
    """
    Request to analyze a stock ticker.

    Attributes:
        symbol (str): The stock symbol to analyze, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).
        intent (str): An optional intent to use for this analysis, which defines the angle of the analysis and the type of insights to return.
    """

    symbol: str = ""
    intent: str = service_analyze_ticker.DEFAULT_INTENT


# ----------------------------------------------------------------------#


class AnalyzePortfolioRequest(BaseRequest):
    """
    Request to build a new portfolio or review an existing one.

    Attributes:
        current_allocation (list[models.HoldingTicker]): A list of current holding tickers in the portfolio.
        country (str): The country code of the portfolio (e.g. AU for Australia).
        investor_theme (str): (optional) The investor's theme/style, e.g. '- Risk tolerance: moderate\n- Time horizon: 5-10 years\n- Goal: capital growth\n- Rebalance frequency: semi-annual'.
    """

    current_allocation: list[models.HoldingTicker] = []
    country: str = ""
    investor_theme: str = services_ai.DEFAULT_INVESTOR_THEME


class AnalyzePortfolioResponse(AnalysisResponse):
    """
    Response schema, containing the analysis result of a portfolio request.
    """

    pass


# ----------------------------------------------------------------------#


class AIVendorsResponse(BaseResponse):
    """
    Response schema, containing the list of available AI vendors and enabled API tiers and models.

    Attributes:
        data (dict[str, ai_models.AIVendorInfo]): A dictionary where the key is the vendor name, and the value is an object containing the vendor information, including supported API tiers and models.
    """

    data: dict[str, models_ai.AIVendorInfo] = {}


# ----------------------------------------------------------------------#


class AnalyzeDividendEventResponse(BaseResponse):
    """
    Response schema, containing the analysis result of a dividend event.

    Attributes:
        data (models_event.DividendEventAnalysis): An object containing the analysis result of the dividend event.
    """

    data: models_event.DividendEventAnalysis | None = None
