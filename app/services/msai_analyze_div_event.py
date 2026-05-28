import json

import yfinance as yf

from ..models import ai as models_ai
from ..models import event as models_event
from ..models import types
from ..services import ai_helper
from ..services import stock as services_stock
from ..utils import conv, yfutils

DEFAULT_INTENT = "Looking to capture the dividend or if post-div dip is worth buying"

BUILD_PROMPT_TEMPLATE = (
    "You are an expert financial analyst and prompt engineer specialising in dividend strategies.\n"
    "\n"
    "Your task is to write a detailed, ready-to-execute prompt that instructs a premium AI model\n"
    "to analyze a dividend event and recommend one of three strategies:\n"
    '- "Dividend Capture": buy before ex-div date to capture the dividend, then exit\n'
    '- "Post-Ex-Div Discount": buy after ex-div date at a depressed price, hold for price recovery\n'
    '- "N/A": insufficient data or conditions do not favour either strategy\n'
    "\n"
    "## Dividend event details\n"
    "- Ticker:           {ticker}\n"
    "- Company name:     {name}\n"
    "- Dividend amount:  {div_amount}\n"
    "- Ex-dividend date: {ex_div_date}\n"
    "- Current price:    {price}\n"
    "- Dividend yield:   {div_yield}\n"
    "- Asset type:       {asset_type}\n"
    "{sector_industry}"
    "- Exchange:         {exchange}\n"
    "- Market cap:       {market_cap_tier}\n"
    "\n"
    "## Investor context\n"
    "- Target market:    {market}\n"
    "- Intent:           {intent}\n"
    "\n"
    "## Your instructions\n"
    "Write a prompt that instructs the premium model to:\n"
    "\n"
    "1. Use web search to gather all data required for a rigorous dividend strategy analysis:\n"
    "   - Historical ex-div price drop behaviour for this ticker (last 4–8 dividend cycles)\n"
    "   - Typical price recovery pattern and timeframe post ex-div\n"
    "   - Current short interest % and any recent changes\n"
    "   - News sentiment in the last 30 days (earnings, guidance, macro headwinds, analyst changes)\n"
    "   - Any upcoming events that could disrupt recovery (earnings, FDA decisions, index rebalancing)\n"
    "   - Tax treatment of this dividend for {market} (e.g. franking credits on ASX,\n"
    "     qualified vs ordinary on US markets, withholding tax for foreign investors)\n"
    "\n"
    "2. Compute or estimate the following fields with full working shown before the JSON output:\n"
    "   - sent_score: sentiment score from -1.0 (very negative) to +1.0 (very positive),\n"
    "     derived from news tone, analyst moves, and short interest direction\n"
    "   - recov_prob_adj: probability (0.00–1.00) that price recovers to pre-ex-div level\n"
    "     within a reasonable timeframe, adjusted for current sentiment and market conditions\n"
    "   - eff_div: effective dividend yield net of tax for {market},\n"
    "     e.g. if franking credits apply, gross up accordingly; if withholding tax applies, net down\n"
    "   - recovery_days: estimated min–max calendar days for price to recover post ex-div,\n"
    '     based on historical patterns; use "N/A" if data is insufficient\n'
    "   - est_drop_price: estimated price range immediately after ex-div date (min–max);\n"
    '     use "N/A" if insufficient data\n'
    "   - est_recovery_price: estimated price range once recovery is complete (min–max);\n"
    '     use "N/A" if insufficient data\n'
    "   - expected_pl: expected P&L per share for the recommended strategy, net of dividend received\n"
    "     or discount captured, expressed as a dollar amount (can be negative)\n"
    "   - confidence: integer 0–100 reflecting overall confidence in the recommendation,\n"
    "     penalised for data gaps, high short interest, upcoming risk events, or low liquidity\n"
    "   - risk: integer 0–100 reflecting overall risk level of the recommended strategy\n"
    "     (0 = minimal risk, 100 = extreme risk)\n"
    "\n"
    "3. Apply the following decision logic to select strategy:\n"
    '   - "Dividend Capture" if ALL of these hold:\n'
    "       * eff_div is meaningful after tax and transaction costs\n"
    "       * sent_score >= 0.1 (neutral to positive sentiment)\n"
    "       * recov_prob_adj is not a concern for this strategy (capture is pre-ex-div)\n"
    "       * No major adverse events between now and ex-div date\n"
    "       * Liquidity is sufficient to enter and exit cleanly\n"
    '   - "Post-Ex-Div Discount" if ALL of these hold:\n'
    "       * Historical drop is typically larger than dividend amount (market overreacts)\n"
    "       * recov_prob_adj >= 0.60\n"
    "       * sent_score >= 0.0 (at minimum neutral)\n"
    "       * recovery_days is within a timeframe acceptable for a short-term trade\n"
    "       * No major adverse events likely to suppress recovery\n"
    '   - "N/A" if:\n'
    "       * Insufficient historical data to estimate drop or recovery\n"
    "       * sent_score < 0.0 (negative sentiment outweighs dividend opportunity)\n"
    "       * recov_prob_adj < 0.60 and strategy would be Post-Ex-Div\n"
    "       * A material risk event falls within the capture or recovery window\n"
    "       * confidence < 40 after penalisation\n"
    "\n"
    "4. Adapt analysis to asset type and market:\n"
    "   - For REITs: note that distributions may be treated as income not capital gains\n"
    "   - For ETFs: note that ex-div drop is mechanical and recovery may be slower\n"
    "   - For ASX stocks: factor in franking credits for Australian tax residents\n"
    "   - For small/micro-cap: heavily penalise confidence due to liquidity and volatility risk\n"
    "   - For special/one-off dividends: note that price behaviour may differ from regular dividends\n"
    "\n"
    "5. Bias the analysis toward investor intent - if the investor has a stated lean,\n"
    "   the premium model should validate or refute it with evidence rather than ignoring it.\n"
    "\n"
    "## Output format rules for the premium model\n"
    "Instruct the premium model to:\n"
    "- Output raw JSON only. No markdown, no backticks, no prose outside the JSON object.\n"
    "\n"
    "```json\n"
    "{{\n"
    '  "search_summary": "2–3 sentences covering news tone, short interest %, key events, and any data gaps",\n'
    '  "strategy": "Dividend Capture|Post-Ex-Div Discount|N/A",\n'
    '  "reasoning": "Key drivers and any failed criteria (max 3 sentences)",\n'
    '  "sent_score": 0.00,\n'
    '  "recov_prob_adj": 0.00,\n'
    '  "eff_div": 0.0000,\n'
    '  "recovery_days": "min-max round up, or N/A",\n'
    '  "est_drop_price": "min-max or N/A",\n'
    '  "est_recovery_price": "min-max or N/A",\n'
    '  "expected_pl": 0.000,\n'
    '  "confidence": 0,\n'
    '  "risk": 0,\n'
    '  "risk_factors": ["list only factors that apply"]\n'
    "}}\n"
    "```\n"
    "- All numeric fields must be numbers, not strings (except fields explicitly noted as strings)\n"
    '- "recovery_days", "est_drop_price", and "est_recovery_price" must be quoted strings\n'
    '  (e.g. "3-7", "N/A") since they represent ranges, not single values\n'
    '- "risk_factors" must only list factors that materially apply - do not pad with generic risks\n'
    "- Do not wrap the JSON in any explanation after the closing brace\n"
    "\n"
    "## Output format\n"
    "Return ONLY the ready-to-use prompt. No preamble, no explanation, no commentary.\n"
    "The prompt must be self-contained - the premium model will receive it with no other context.\n"
    "The prompt must instruct the premium model to use the hyphen (-) instead of em-dash (\u2014) throughout."
)


def _build_analysis_prompt(
    *,
    ticker: yf.Ticker,
    pre_result: models_event.DividendEventAnalysis,
    intent: str = DEFAULT_INTENT,
) -> str:
    """Build the meta-prompt that instructs the AI to produce a dividend event analysis prompt."""
    info = ticker.info
    asset_type = yfutils.detect_asset_type(ticker=ticker)
    cap_size, market_index = yfutils.classify_market_cap(ticker)

    # Sector/Industry only relevant for EQUITY and REIT
    if asset_type in (types.STANDARD_ASSET, types.REIT_ASSET, types.LIC_ASSET):
        sector_industry = (
            f"- Sector:           {info.get('sector') or '(n/a)'}\n"
            f"- Industry:         {info.get('industry') or '(n/a)'}\n"
        )
    else:
        sector_industry = ""

    return BUILD_PROMPT_TEMPLATE.format(
        ticker=info.get("symbol") or "(n/a)",
        name=info.get("longName") or info.get("shortName") or "(n/a)",
        div_amount=pre_result.div_amount,
        # ex_div_date=pre_result.ex_div_date,
        ex_div_date=pre_result.date,
        price=pre_result.price,
        div_yield=f"{pre_result.div_yield:.2%}",
        asset_type=asset_type,
        sector_industry=sector_industry,
        exchange=pre_result.exchange,
        market_cap_tier=(
            f"{cap_size} ({market_index})" if cap_size and market_index else f"{cap_size}" if cap_size else "(n/a)"
        ),
        market=ticker.info.get("country") or "(n/a)",
        intent=intent if intent else DEFAULT_INTENT,
    )


async def ai_analyze_div_event(
    *,
    symbol: str,
    ex_date: str,
    div_amount: float,
    intent: str = DEFAULT_INTENT,
) -> models_event.DividendEventAnalysis | None:
    """
    Analyze a dividend event using AI assistance.

    Args:
        symbol (str): The stock symbol to analyze, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).
        ex_date (str): Ex-dividend date in ISO format (YYYY-MM-DD).
        div_amount (float): Dividend amount per share.
        intent (str, optional): The intent to use for this analysis. Defaults to DEFAULT_INTENT.

    Returns:
        models_ai.AnalysisResult | None: A models_ai.AnalysisResult object containing the analysis, or None.
    """
    # Step 1: ticker validation & analysis based on historical data
    yf_ticker = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_ticker)
    result = await services_stock.analyse_dividend_event(
        ticker=ticker, symbol=symbol, ex_date=ex_date, div_amount=div_amount
    )
    if not result:
        return None

    # Step 2: use AI to build the ready-to-use prompt
    build_prompt_input = _build_analysis_prompt(ticker=ticker, pre_result=result, intent=intent)

    country = conv.country_to_iso2(ticker.info.get("country", ""))
    llm_result = await ai_helper.ai_exec_task("ANALYZE_DIV_EVENT_BUILD_PROMPT", build_prompt_input, country)
    if llm_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=llm_result.error_msg)

    analysis_prompt = llm_result.completion

    # Step 3: execute the prompt built from previous step
    exec_result = await ai_helper.ai_exec_task("ANALYZE_DIV_EVENT_EXEC", analysis_prompt, country)
    if exec_result.is_error:
        result.llm_error = True
        result.llm_error_msg = f"LLM failed to generate response for analyzing dividend event: {exec_result.error_msg}"
        return result

    llm_result_obj = json.loads(exec_result.completion)
    result.search_summary = llm_result_obj.get("search_summary")
    result.strategy = llm_result_obj.get("strategy")
    result.reasoning = llm_result_obj.get("reasoning")
    result.sentiment_score = llm_result_obj.get("sent_score")
    # result.sentiment_score = float(result.sentiment_score) if result.sentiment_score is not None else None
    result.recovery_probability_adj = llm_result_obj.get("recov_prob_adj")
    # result.recovery_probability_adj = (
    #     float(result.recovery_probability_adj) if result.recovery_probability_adj is not None else None
    # )
    result.recovery_days_adj = llm_result_obj.get("recovery_days")
    result.drop_price_adj = llm_result_obj.get("est_drop_price")
    result.recovery_price_adj = llm_result_obj.get("est_recovery_price")
    result.expected_pl = llm_result_obj.get("expected_pl")
    # result.expected_pl = float(result.expected_pl) if result.expected_pl is not None else None
    result.confidence_level = llm_result_obj.get("confidence")
    # result.confidence_level = float(result.confidence_level) if result.confidence_level is not None else None
    result.risk_level = llm_result_obj.get("risk")
    # result.risk_level = float(result.risk_level) if result.risk_level is not None else None

    return result
