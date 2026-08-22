from ..models import ai as models_ai
from ..models import portfolio as models_portfolio
from ..services import ai as services_ai
from ..services import msai_analyze_ticker as service_analyze_ticker
from . import async_task
from .base_req_resp import BaseRequest, BaseResponse


class AnalysisResponse(BaseResponse[models_ai.AnalysisResult]):
    """
    Response schema, containing the analysis result from an AI model.

    Attributes:
        data (models.AnalysisResponse): An object containing the analysis response of the AI model.
    """


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
        current_allocation (list[models_portfolio.PortfolioHolding]): A list of current holdings in the portfolio.
        country (str): The country code of the portfolio (e.g. AU for Australia).
        investor_theme (str): (optional) The investor's theme/style, e.g. '- Risk tolerance: moderate\n- Time horizon: 5-10 years\n- Goal: capital growth\n- Rebalance frequency: semi-annual'.
        rebalance_plan (bool): (optional) Whether to assess the need for a major rebalance and generate a plan when needed.
    """

    country: str
    current_allocation: list[models_portfolio.PortfolioHolding] = []
    investor_theme: str = services_ai.DEFAULT_INVESTOR_THEME
    rebalance_plan: bool = False


class AnalyzePortfolioResponse(AnalysisResponse):
    """
    Response schema, containing the analysis result of a portfolio request.
    """

    pass


class ReviewPortfolioResponse(BaseResponse[models_ai.AnalyzePortfolioResult]):
    """
    Response schema, containing the analysis result of a portfolio review.
    """


# ----------------------------------------------------------------------#


class AIVendorsResponse(BaseResponse[dict[str, models_ai.AIVendorInfo]]):
    """
    Response schema, containing the list of available AI vendors and enabled API tiers and models.

    Attributes:
        data (dict[str, ai_models.AIVendorInfo]): A dictionary where the key is the vendor name, and the value is an object containing the vendor information, including supported API tiers and models.
    """

    data: dict[str, models_ai.AIVendorInfo] = {}


# ----------------------------------------------------------------------#


class AnalyzeTickerAsyncResponse(async_task.AsyncTaskResponse[models_ai.AnalysisResult]):
    pass


class BuildPortfolioAsyncResponse(async_task.AsyncTaskResponse[models_ai.AnalyzePortfolioResult]):
    pass


class AnalyzePortfolioAsyncResponse(async_task.AsyncTaskResponse[models_ai.AnalyzePortfolioResult]):
    pass
