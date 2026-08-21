import datetime

from pydantic import ConfigDict, Field

from ..models import events_dividends as models_events_dividends
from . import events as schemas_events
from .base_req_resp import BaseRequest, BaseResponse


class AnalyzeDividendEventRequest(BaseRequest):
    """
    Request to research and assess a dividend event.

    Attributes:
        symbol: Stock symbol in Yahoo Finance or EXCHANGE:CODE format.
        ex_date: Ex-dividend date used to derive the event phase.
        dividend_amount: Positive gross cash dividend per share.
        transaction_costs: Optional round-trip per-share costs for each strategy.
        holding_period_days: Calendar-day window used for recovery and strategy estimates.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        min_length=1,
        max_length=128,
        description="Stock symbol in Yahoo Finance format (for example, CBA.AX) or EXCHANGE:CODE format (for example, NASDAQ:AAPL).",
    )
    ex_date: datetime.date = Field(
        description="Ex-dividend date; the service interprets it relative to the exchange-local date."
    )
    dividend_amount: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive finite gross cash dividend per share in the instrument's trading currency.",
    )
    transaction_costs: models_events_dividends.DividendTransactionCosts = Field(
        default_factory=models_events_dividends.DividendTransactionCosts,
        description="Round-trip per-share costs for dividend capture and post-dividend discount strategies; omitted costs default to zero.",
    )
    holding_period_days: int = Field(
        default=28,
        ge=1,
        le=365,
        description="Calendar-day window used to estimate recovery and strategy outcomes; defaults to 28 days.",
    )


class AnalyzeDividendEventResponse(BaseResponse):
    data: models_events_dividends.DividendEventAnalysis | None = None


class AnalyzeDividendEventAsyncResponse(AnalyzeDividendEventResponse):
    extra: schemas_events.AsyncTaskInfo
