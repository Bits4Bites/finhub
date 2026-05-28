import yfinance as yf

from .. import config
from ..models.ai import AnalysisResult
from ..models.types import LIC_ASSET, REIT_ASSET, STANDARD_ASSET
from ..services import ai_helper
from ..utils import yfutils
from ..utils.conv import country_to_iso2, normalize_exchange_code, to_yf_symbol_format
from ..utils.yfutils import classify_market_cap

DEFAULT_INTENT = (
    "One-page analysis and Stock outlook with trend and price range prediction for the next 2 weeks, 1 month, and 3 months. "
    "Include confidence level (low/medium/high) for each outlook period."
)

BUILD_PROMPT_TEMPLATE = (
    "You are an expert financial analyst and prompt engineer.\n"
    "\n"
    "Your task is to write a ready-to-execute prompt that instructs a premium AI model to perform a stock analysis,\n"
    "adapt to the following intent: {intent}\n"
    "\n"
    "## Stock to analyze\n"
    "- Ticker:     {ticker}\n"
    "- Name:       {name}\n"
    "- Asset type: {asset_type}\n"
    "{sector_industry}"
    "- Exchange:   {exchange}\n"
    "- Market cap: {market_cap_tier}\n"
    "\n"
    "## Your instructions\n"
    "Adapt the analysis prompt to the intent, and the nature of this specific asset:\n"
    "- For ETFs/funds: focus on holdings, expense ratio, tracking error, liquidity\n"
    "- For REITs: focus on FFO, AFFO, occupancy, dividend sustainability, debt structure\n"
    "- For foreign equities: include currency risk, local regulations, geopolitical factors\n"
    "- For small/micro-cap: flag liquidity risk, limited analyst coverage, higher volatility\n"
    "- For sector-specific equities: include the key metrics that matter most for that sector\n"
    "\n"
    "Write a ready-to-execute prompt that tells the premium model to:\n"
    "1. Use its web search capability to gather current, real data on the stock\n"
    "2. Structure the analysis clearly with defined sections\n"
    "3. Support every claim with data (numbers, dates, sources)\n"
    "4. Conclude with a balanced, evidence-based investment view\n"
    "\n"
    "## The prompt must instruct the premium model to cover (adapted to intent and asset type):\n"
    "- Detailed/Brief asset overview (business model or fund objective, sector, market cap tier)\n"
    "- Recent financial performance (metrics relevant to this asset type)\n"
    "- Valuation (multiples relevant to this asset type vs. appropriate peers)\n"
    "- Growth catalysts and risks (including country/currency risk if applicable)\n"
    "- Recent news and sentiment (last 30 days)\n"
    "- Analyst or fund consensus and price/NAV targets where available\n"
    "- Stock outlook with trend prediction for the next 2 weeks, 1 month, and 3 months\n"
    "- Confidence level (low/medium/high) for each outlook period\n"
    "- A final investment summary (bullish / neutral / bearish case)"
    "\n"
    "## Output format\n"
    "Return ONLY the ready-to-execute prompt. No preamble, no explanation, no commentary.\n"
    "The prompt must be self-contained, the premium model will receive it with no other context.\n"
    "The prompt must instruct the premium model to format the response in Markdown, "
    "and use the hyphen character (-) instead of em-dash (\u2014) throughout.\n"
    "The premium model is NOT to include any suggested follow-up questions."
)


def _build_analysis_prompt(*, ticker: yf.Ticker, intent: str = DEFAULT_INTENT) -> str:
    """Build the meta-prompt that instructs the AI to produce a stock analysis prompt."""
    info = ticker.info
    asset_type = yfutils.detect_asset_type(ticker=ticker)
    exchange = normalize_exchange_code(info.get("fullExchangeName") or info.get("exchange") or "")
    cap_size, market_index = classify_market_cap(ticker)

    # Sector/Industry only relevant for EQUITY and REIT
    if asset_type in (STANDARD_ASSET, REIT_ASSET, LIC_ASSET):
        sector_industry = (
            f"- Sector:     {info.get('sector') or '(n/a)'}\n- Industry:   {info.get('industry') or '(n/a)'}\n"
        )
    else:
        sector_industry = ""

    return BUILD_PROMPT_TEMPLATE.format(
        intent=intent if intent else DEFAULT_INTENT,
        ticker=info.get("symbol") or "(n/a)",
        name=info.get("longName") or info.get("shortName") or "(n/a)",
        asset_type=asset_type,
        sector_industry=sector_industry,
        exchange=exchange,
        market_cap_tier=(
            f"{cap_size} ({market_index})" if cap_size and market_index else f"{cap_size}" if cap_size else "(n/a)"
        ),
    )


async def ai_analyze_ticker(symbol: str, *, intent: str = DEFAULT_INTENT) -> AnalysisResult | None:
    """
    Analyze a ticker using AI.

    Args:
        symbol (str): The stock symbol to analyze, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).
        intent (str, optional): The intent to use for this analysis. Defaults to DEFAULT_INTENT.

    Returns:
        AnalysisResult | None: A AnalysisResult object containing the analysis, or None.
    """
    # Step 1: check if the ticker is valid
    yf_ticker = to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_ticker)
    quote_type = ticker.info.get("quoteType")
    if quote_type not in config.ALLOWED_QUOTE_TYPES:
        return None

    # Step 2: use AI to build the ready-to-use prompt to analyze the ticker with the intent
    build_prompt_input = _build_analysis_prompt(ticker=ticker, intent=intent)

    country = country_to_iso2(ticker.info.get("country", ""))
    llm_result = await ai_helper.ai_exec_task("ANALYZE_TICKER_BUILD_PROMPT", build_prompt_input, country)
    if llm_result.is_error:
        return AnalysisResult(llm_error=True, llm_error_msg=llm_result.error_msg)

    analysis_prompt = llm_result.completion

    # Step 3: execute the prompt built from previous step
    exec_result = await ai_helper.ai_exec_task("ANALYZE_TICKER_EXEC", analysis_prompt, country)
    if exec_result.is_error:
        return AnalysisResult(llm_error=True, llm_error_msg=exec_result.error_msg)

    return AnalysisResult(analysis=exec_result.completion)
