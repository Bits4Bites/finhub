import json

import yfinance as yf
from datetime import datetime, timezone

from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from . import ai_helper
from ..models import finhub as models, types
from ..config import settings_llm
from ..services import crawler as crawler_service, stock as stock_service
from ..utils import finhub as finhub_utils

EVENT_ASX_NEW_LISTINGS = "ASX_NEW_LISTING_EVENTS"
ANALYZE_ASX_LISTINGS = "ASX_LISTINGS_ANALYSIS"
ANALYZE_ASX_DIVIDEND = "ASX_DIVIDEND_ANALYSIS"
ANALYZE_US_DIVIDEND = "US_DIVIDEND_ANALYSIS"
ANALYZE_VN_DIVIDEND = "VN_DIVIDEND_ANALYSIS"


prompts: dict[str, str] = {}


async def ai_exec_prompt(
    task_id: str, prompt: str, country: str = None, thinking_level: str = None
) -> models.LLMResponse:
    """
    Executes a prompt using the appropriate LLM based on the task configuration.
    """
    task_cfg = settings_llm.llm_task_config.get(task_id)
    if not task_cfg:
        raise ValueError(f"LLM task configuration for task_id '{task_id}' not found.")
    prompt_cfg = ai_helper.PromptConfig(
        use_web_search=task_cfg.model.startswith("gpt-5"),
        country=country,
        thinking_level=thinking_level,
    )
    return await ai_helper.ai_exec_prompt(task_cfg, prompt, prompt_cfg)


# ----------------------------------------------------------------------#


async def _get_asx_new_listings() -> list[models.ListingEvent]:
    event_type = EVENT_ASX_NEW_LISTINGS
    prompt_template = prompts[event_type] if event_type in prompts else ""
    if not prompt_template:
        raise EnvironmentError(f"Prompt template for {event_type} is missing or empty.")

    url = "https://www.asx.com.au/listings/upcoming-floats-and-listings"
    html_content = await crawler_service.fetch_webpage_content(url)
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    el_list = soup.select("div.multi-column-height")
    # join all the text from the elements, only if it contains the string "Listing date"
    raw_input = "==========\n".join([el.get_text() for el in el_list if "Listing date" in el.get_text()])
    prompt = prompt_template.replace("{RAW_INPUT_DATA}", raw_input)

    sectors_list = ",".join(finhub_utils.asx_sector_yf_static_tickers.keys())
    prompt = prompt.replace("{SECTORS}", sectors_list)

    llm_result = await ai_exec_prompt(task_id="PARSE_NEW_LISTING_EVENTS_NO_WEB_SEARCH", prompt=prompt, country="AU")
    if llm_result.is_error:
        raise RuntimeError(f"[ERROR] LLM failed to generate response for new listing events: {llm_result.completion}")

    default_vals = {
        "currency": "AUD",
        "exchange": "ASX",
        "src": "ASX",
        "link": "https://www.asx.com.au/listings/upcoming-floats-and-listings",
    }
    return models.parse_new_listing_events_from_json(llm_result.completion, default_vals)


async def _analyze_asx_listings(events: list[models.ListingEvent]) -> list[models.ListingEvent]:
    if len(events) == 0:
        return events

    event_type = ANALYZE_ASX_LISTINGS
    prompt_template = prompts[event_type] if event_type in prompts else ""
    if not prompt_template:
        return events
        # raise EnvironmentError(f"Prompt template for {event_type} is missing or empty.")

    # prepare input data for LLM
    tz = ZoneInfo("Australia/Sydney")
    now = datetime.now(tz).strftime("%Y-%m-%d")
    companies = ""
    for e in events:
        companies += f"{e.symbol} ({e.company_name})"
        if now > e.date:
            companies += f" | Listed: {e.date} (${e.price:.2f})"
        else:
            companies += f" | IPO: {e.date} (${e.price:.2f})"
        companies += f" | MCap: ${finhub_utils.number_to_human_format(e.capital, 2)}"
        companies += f" | Sector: {e.sector}"
        companies += f" | Activities: {e.principal_activities}"
        companies += "\n"

    prompt = prompt_template.replace("{COMPANIES}", companies)
    llm_result = await ai_exec_prompt(task_id="ANALYZE_DIVIDEND_EVENT_WEB_SEARCH", prompt=prompt, country="AU")
    if llm_result.is_error:
        return events
        # raise RuntimeError(f"[ERROR] LLM failed to generate response for new listing events: {llm_result.completion}")

    analysis = models.parse_listing_analysis_from_json(llm_result.completion, {})
    for e in events:
        if e.symbol in analysis:
            e.analysis = analysis[e.symbol]

    return events


async def ai_get_asx_new_listings() -> list[models.ListingEvent]:
    """
    Check for new listings for ASX, using AI assistance.

    Returns:
        list[models.ListingEvent]: A list of new listing events
    """
    events = await _get_asx_new_listings()
    events = await _analyze_asx_listings(events)
    tz = ZoneInfo("Australia/Sydney")
    for event in events:
        event.date = finhub_utils.yyyy_mm_dd_to_iso(event.date, tz)
        event.timestamp = int(datetime.fromisoformat(event.date).timestamp())
    return events


# ----------------------------------------------------------------------#

dividend_capture_shortscore_rules = {
    "ASX": {
        types.LARGE_CAP: "<1.5%:0 | 1.5–3%:-0.12 | 3–6%: -0.24 | >6%: -0.36",
        types.MID_CAP: "<2%:0 | 2–4%:-0.14 | 4–8%: -0.30 | >8%: -0.42",
        types.SMALL_CAP: "<3%:0 | 3–6%:-0.18 | 6–10%: -0.36 | >10%: -0.48",
        types.MICRO_CAP: "<4%:0 | 4-8%:-0.24 | 8–15%: -0.42 | >15%: -0.60",
        types.NANO_CAP: "<5%:0 | 5-10%:-0.30 | 10-20%: -0.48 | >20%: -0.72",
    },
    "NASDAQ": {
        types.LARGE_CAP: "<1.5%:0 | 1.5–3%:-0.08 | 3–6%: -0.16 | >6%: -0.24",
        types.MID_CAP: "<2%:0 | 2–4%:-0.10 | 4–8%: -0.20 | >8%: -0.28",
        types.SMALL_CAP: "<3%:0 | 3–6%:-0.12 | 6–10%: -0.24 | >10%: -0.32",
        types.MICRO_CAP: "<4%:0 | 4-8%:-0.16 | 8–15%: -0.28 | >15%: -0.40",
        types.NANO_CAP: "<5%:0 | 5-10%:-0.20 | 10-20%: -0.32 | >20%: -0.48",
    },
    "NYSE": {
        types.LARGE_CAP: "<1.5%:0 | 1.5–3%:-0.10 | 3–6%: -0.20 | >6%: -0.30",
        types.MID_CAP: "<2%:0 | 2–4%:-0.12 | 4–8%: -0.25 | >8%: -0.35",
        types.SMALL_CAP: "<3%:0 | 3–6%:-0.15 | 6–10%: -0.30 | >10%: -0.40",
        types.MICRO_CAP: "<4%:0 | 4-8%:-0.20 | 8–15%: -0.35 | >15%: -0.50",
        types.NANO_CAP: "<5%:0 | 5-10%:-0.25 | 10-20%: -0.40 | >20%: -0.60",
    },
}

dividend_capture_criteria = {
    "ASX": {
        types.LARGE_CAP: [  # >= 10B
            "AdjRecovProb ≥65%",
            "ExpectedPL ≥1.5%",
            "Yield ≥2.0%",
            "EstRecovDays(max) ≤5",
            "Spread <0.003",
            "RSI14 <70",
            "Short Interest <5.0%",
            "IndTrend60d >-2.0%",
            "TrendVsInd60d >-1.0%",
            "AvgDVT7d >20M",
            "Liquidity >0.0006",
        ],
        types.MID_CAP: [  # 2B-10B
            "AdjRecovProb ≥70%",
            "ExpectedPL ≥2.0%",
            "Yield ≥3.0%",
            "EstRecovDays(max) ≤7",
            "Spread <0.008",
            "RSI14 <65",
            "Short Interest <4.0%",
            "IndTrend60d >-1.0%",
            "TrendVsInd60d >-0.5%",
            "AvgDVT7d >5M",
            "Liquidity >0.00048",
        ],
        types.SMALL_CAP: [  # 300M-2B
            "AdjRecovProb ≥75%",
            "ExpectedPL ≥3.0%",
            "Yield ≥4.5%",
            "EstRecovDays(max) ≤10",
            "Spread <0.015",
            "RSI14 <60",
            "Short Interest <2.5%",
            "IndTrend60d >0.0%",
            "TrendVsInd60d >0.0%",
            "AvgDVT7d >1M",
            "Liquidity >0.00036",
        ],
        types.MICRO_CAP: [  # 50M-300M
            "AdjRecovProb ≥85%",
            "ExpectedPL ≥5.0%",
            "Yield ≥6.5%",
            "EstRecovDays(max) ≤14",
            "Spread <0.025",
            "RSI14 <55",
            "Short Interest <1.5%",
            "IndTrend60d >1.0%",
            "TrendVsInd60d >1.0%",
            "AvgDVT7d >250K",
            "Liquidity >0.00024",
        ],
        types.NANO_CAP: [  # <50M
            "AdjRecovProb ≥90%",
            "ExpectedPL ≥7.0%",
            "Yield ≥8.5%",
            "EstRecovDays(max) ≤21",
            "Spread <0.030",
            "RSI14 <50",
            "Short Interest <1.0%",
            "IndTrend60d >2.0%",
            "TrendVsInd60d >2.0%",
            "AvgDVT7d >50K",
            "Liquidity >0.00012",
        ],
    },
    "NASDAQ": {
        types.LARGE_CAP: [  # >= 10B
            "AdjRecovProb ≥65%",
            "EstRecovDays(max) ≤3",
            "ExpectedPL ≥0.5%",
            "Yield ≥0.5%",
            "Spread <0.0005",
            "Beta <1.1",
            "RSI14 <65",
            "Short Interest <3.0%",
            "IndTrend60d >-2.0%",
            "TrendVsInd60d >-1.0%",
            # "AvgDVT7d >100M",
            "Liquidity >0.0004",
        ],
        types.MID_CAP: [  # 2B-10B
            "AdjRecovProb ≥70%",
            "EstRecovDays(max) ≤5",
            "ExpectedPL ≥1.0%",
            "Yield ≥1.0%",
            "Spread <0.0015",
            "Beta <1.0",
            "RSI14 <60",
            "Short Interest <2.0%",
            "IndTrend60d >-1.0%",
            "TrendVsInd60d >-0.5%",
            # "AvgDVT7d >20M",
            "Liquidity >0.00032",
        ],
        types.SMALL_CAP: [  # 300M-2B
            "AdjRecovProb ≥80%",
            "EstRecovDays(max) ≤8",
            "ExpectedPL ≥1.5%",
            "Yield ≥1.5%",
            "Spread <0.004",
            "Beta <0.9",
            "RSI14 <55",
            "Short Interest <1.0%",
            "IndTrend60d >0.0%",
            "TrendVsInd60d >0.0%",
            # "AvgDVT7d >5M",
            "Liquidity >0.00024",
        ],
    },
    "NYSE": {
        types.LARGE_CAP: [  # >= 10B
            "AdjRecovProb ≥60%",
            "EstRecovDays(max) ≤4",
            "ExpectedPL ≥0.8%",
            "Yield ≥1.0%",
            "Spread <0.001",
            "RSI14 <70",
            "Short Interest <4.0%",
            "IndTrend60d >-2.0%",
            "TrendVsInd60 >-1.0%",
            # "AvgDVT7d >50M",
            "Liquidity >0.0005",
        ],
        types.MID_CAP: [  # 2B-10B
            "AdjRecovProb ≥65%",
            "EstRecovDays(max) ≤6",
            "ExpectedPL ≥1.2%",
            "Yield ≥1.5%",
            "Spread <0.0025",
            "RSI14 <65",
            "Short Interest <3.0%",
            "IndTrend60d >-1.0%",
            "TrendVsInd60d >-0.5%",
            # "AvgDVT7d >10M",
            "Liquidity >0.0004",
        ],
        types.SMALL_CAP: [  # 300M-2B
            "AdjRecovProb ≥75%",
            "EstRecovDays ≤10",
            "ExpectedPL ≥2.0%",
            "Yield ≥2.5%",
            "Spread <0.005",
            "RSI14 <60",
            "Short Interest <2.0%",
            "IndTrend60d >0.0%",
            "TrendVsInd60d >0.0%",
            # "AvgDVT7d >2M",
            "Liquidity >0.0003",
        ],
    },
}


async def ai_analyse_dividend_event(
    *,
    symbol: str,
    ex_date: str,
    div_amount: float,
) -> models.DividendEventAnalysis | None:
    """
    Analyzes a dividend event using AI assistance.

    Args:
        symbol (str): Stock ticker symbol (e.g., 'AAPL', 'BHP.AX', 'HOSE:BID' etc.).
        ex_date (str): Ex-dividend date in ISO format (YYYY-MM-DD).
        div_amount (float): Dividend amount per share.

    Returns:
        models.DividendEventAnalysis: An object containing the analysis of the dividend event
    """
    yf_ticker = finhub_utils.to_yf_ticker(symbol)
    ticker = yf.Ticker(yf_ticker)
    result = await stock_service.analyse_dividend_event(
        ticker=ticker, symbol=symbol, ex_date=ex_date, div_amount=div_amount
    )
    if not result:
        return None

    # country = finhub_utils.country_code_from_yf_ticker(yf_ticker)
    country = result.overview.country
    event_type = (
        ANALYZE_ASX_DIVIDEND if country == "AU" else ANALYZE_VN_DIVIDEND if country == "VN" else ANALYZE_US_DIVIDEND
    )
    prompt_template = prompts[event_type] if event_type in prompts else ""
    if not prompt_template:
        result.llm_error = True
        result.llm_error_msg = f"Prompt template for {event_type} is missing or empty."
        return result

    # CONTEXT
    today_utc = datetime.now(timezone.utc).date()
    prompt = (
        prompt_template.replace("{TICKER}", finhub_utils.to_yf_ticker(result.overview.symbol))
        .replace("{INDUSTRY}", f"{result.overview.industry}")
        .replace("{TODAY}", today_utc.isoformat())
        .replace("{CURRENT_PRICE}", f"{result.price:.2f}")
        .replace("{EX_DIV_DATE}", ex_date)
        .replace("{DIV_AMOUNT}", f"{div_amount:.2f}")
        .replace("{DIV_YIELD}", f"{result.div_yield:.2%}")
    )

    # TECHNICALS
    trend_vs_industry = (
        result.trend_60d - result.peer_trend_60d if result.peer_trend_60d is not None else result.trend_60d
    )
    industry_trend_str = (
        f"{result.peer_trend_60d:.2%}"
        if result.peer_trend_60d is not None
        else f"{result.market_trend_60d}" if result.market_trend_60d is not None else "N/A"
    )
    cap_size, market_index = finhub_utils.classify_market_cap(ticker)
    cap_size_str = ""
    if cap_size is not None:
        cap_size_str = f"({cap_size}"
        if market_index is not None:
            cap_size_str += f",{market_index}"
        cap_size_str += ")"
    bid_ask_spread_str = f"{result.bid_ask_spread:.4f}" if result.bid_ask_spread is not None else "N/A"
    past_dividends_analysis = f"HistExDiv(absolute prices, n={result.num_samples}): DropPriceRange:{result.drop_price_min:.2f}-{result.drop_price_max:.2f}|RecovPriceRange:{result.recovery_price_min:.2f}-{result.recovery_price_min:.2f}|RecovDays:{result.recovery_days_min:.0f}-{result.recovery_days_max:.0f}|RecovProb:{result.recovery_probability:.0%}"
    # history30d = ticker.history(period="31d", interval="1d", auto_adjust=False)[:-1]
    # vol_spikes_str = "VolSpikes:None"
    # vol_spike_series = finhub_utils.find_volume_spikes(history30d, 2)
    # if not vol_spike_series.empty:
    #     vol_spikes_str = "VolSpikes(Date,Close,Vol):"
    #     for index, row in vol_spike_series.iterrows():
    #         vol_spikes_str += f"{index.strftime("%Y-%m-%d")},{row["Close"]:.2f},{finhub_utils.number_to_human_format(row["Volume"], 2)}|"
    #     vol_spikes_str = vol_spikes_str[:-1]
    prompt = (
        prompt.replace("{BETA}", f"{result.beta:.2f}")
        .replace("{RSI}", f"{int(result.rsi14)}")
        .replace("{RSI14}", f"{int(result.rsi14)}")
        .replace("{RSI-14}", f"{int(result.rsi14)}")
        .replace("{INDUSTRY_TREND}", f"{industry_trend_str}")
        .replace("{TREND_VS_INDUSTRY}", f"{trend_vs_industry:.2%}")
        .replace("{AVG_VOL}", f"{finhub_utils.number_to_human_format(result.avg_volume_30d, 0)}")
        .replace("{AVG_DVT}", f"{finhub_utils.number_to_human_format(result.avg_dvt_7d, 0)}")
        .replace("{MARKET_CAP}", f"{finhub_utils.number_to_human_format(result.overview.market_cap, 0)}")
        .replace("{CAP_SIZE}", cap_size_str)
        .replace("{BID_ASK_SPREAD}", bid_ask_spread_str)
        .replace("{PAST_DIVIDENDS_ANALYSIS}", past_dividends_analysis)
        # .replace("{VOLUME_SPIKES}", vol_spikes_str)
        .replace("{RECOVERY_DAYS_MIN}", f"{result.recovery_days_min:.0f}")
        .replace("{RECOVERY_DAYS_MAX}", f"{result.recovery_days_max:.0f}")
        .replace("{DROP_PRICE_MIN}", f"{result.drop_price_min:.2f}")
        .replace("{DROP_PRICE_MAX}", f"{result.drop_price_max:.2f}")
        .replace("{RECOVERY_PRICE_MIN}", f"{result.recovery_price_min:.2f}")
        .replace("{RECOVERY_PRICE_MAX}", f"{result.recovery_price_max:.2f}")
    )

    # CALCULATIONS
    short_score_formula = "0"
    if result.overview.exchange in dividend_capture_shortscore_rules:
        if result.overview.cap_size in dividend_capture_shortscore_rules[result.overview.exchange]:
            short_score_formula = dividend_capture_shortscore_rules[result.overview.exchange][result.overview.cap_size]
    prompt = prompt.replace("{SHORT_SCORE_FORMULA}", short_score_formula)

    # RULES
    div_capture_rules = ""
    if result.overview.exchange in dividend_capture_criteria:
        if result.overview.cap_size in dividend_capture_criteria[result.overview.exchange]:
            criteria = dividend_capture_criteria[result.overview.exchange][result.overview.cap_size]
            for r in criteria:
                div_capture_rules += f"[ ] {r}\n"
            div_capture_rules = div_capture_rules.rstrip("\n")
    prompt = prompt.replace("{DIV_CAPTURE_RULES}", div_capture_rules)

    llm_result = await ai_exec_prompt("ANALYZE_DIVIDEND_EVENT_WEB_SEARCH", prompt, country)
    if llm_result.is_error:
        result.llm_error = True
        result.llm_error_msg = f"LLM failed to generate response for analyzing dividend event: {llm_result.completion}"
        return result

    llm_result_obj = json.loads(llm_result.completion)
    result.search_summary = llm_result_obj.get("search_summary")
    result.strategy = llm_result_obj.get("strategy")
    result.reasoning = llm_result_obj.get("reasoning")
    result.sentiment_score = llm_result_obj.get("sent_score")
    result.sentiment_score = float(result.sentiment_score) if result.sentiment_score is not None else None
    result.recovery_probability_adj = llm_result_obj.get("recov_prob_adj")
    result.recovery_probability_adj = (
        float(result.recovery_probability_adj) if result.recovery_probability_adj is not None else None
    )
    result.recovery_days_adj = llm_result_obj.get("recovery_days")
    result.drop_price_adj = llm_result_obj.get("est_drop_price")
    result.recovery_price_adj = llm_result_obj.get("est_recovery_price")
    result.expected_pl = llm_result_obj.get("expected_pl")
    result.expected_pl = float(result.expected_pl) if result.expected_pl is not None else None
    result.confidence_level = llm_result_obj.get("confidence")
    result.confidence_level = float(result.confidence_level) if result.confidence_level is not None else None
    result.risk_level = llm_result_obj.get("risk")
    result.risk_level = float(result.risk_level) if result.risk_level is not None else None

    return result
