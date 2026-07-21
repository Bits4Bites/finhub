import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import event as models_event
from ..services import crawler as services_crawler
from ..utils import conv
from ..utils import data as data_utils
from . import ai_helper


async def ai_get_asx_new_listings() -> list[models_event.ListingEvent]:
    """
    Check for new listings for ASX, using AI assistance.

    Returns:
        list[models_event.ListingEvent]: A list of new listing events
    """
    events = await _get_asx_new_listings()
    events = await _analyze_asx_listings(events)
    tz = ZoneInfo("Australia/Sydney")
    for event in events:
        event.date = conv.yyyymmdd_to_iso(event.date or "", tz)
        event.timestamp = int(datetime.fromisoformat(event.date or "").timestamp())
    return events


async def _get_asx_new_listings() -> list[models_event.ListingEvent]:
    # Step 1: fetch new listings from ASX website as raw text.
    url = "https://www.asx.com.au/listings/upcoming-floats-and-listings"
    html_content = await services_crawler.fetch_webpage_content(url)
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    el_list = soup.select("div.multi-column-height")
    # join all the text from the elements, only if it contains the string "Listing date"
    raw_input = "==========\n".join([el.get_text() for el in el_list if "Listing date" in el.get_text()])

    # Step 2: use AI to parse the new listings as JSON
    extract_prompt = (
        "TASK: Extract upcoming ASX listings from RAW INPUT DATA into a JSON array. If none, return [].\n"
        "\n"
        "Rules:\n"
        '- Listing date is next to company name (NOT "Expected offer close date").\n'
        "- Skip entries with unconfirmed dates (TBC/TBA/TBD).\n"
        '- public_offer_close_date: extract from "Expected offer close date" and convert to YYYY-MM-DD. '
        'If no "Expected offer close date" info is found, set to null.\n'
        "- price and capital: if the source value is null, blank, missing, unavailable, or cannot be parsed, "
        "output numeric 0. Never output null for these fields.\n"
        "- Map principal_activities to ONE sector from: {SECTORS}\n"
        '  (normalize synonyms, e.g. "INFORMATION TECHNOLOGY" → TECHNOLOGY).\n'
        "\n"
        "Output:\n"
        "- Raw JSON only (no markdown/text), starting with [ and ending with ].\n"
        "\n"
        "Schema:\n"
        "[\n"
        "  {{\n"
        '    "symbol": "ASX:{{TICKER}}",\n"'
        '    "company": "string",\n'
        '    "date": "YYYY-MM-DD",\n'
        '    "price": 0.0,\n'
        '    "principal_activities": "string",\n'
        '    "sector": "string",\n'
        '    "capital": 0,\n'
        '    "public_offer_close_date": "YYYY-MM-DD or null"\n'
        "  }}\n"
        "]\n"
        "\n"
        "Notes:\n"
        "- price: float, strip currency/text; use 0.0 when no value is available.\n"
        "- capital: int, strip currency/commas; use 0 when no value is available.\n"
        "\n"
        "RAW INPUT DATA:\n"
        "{RAW_INPUT_DATA}\n"
    )
    sectors_list = ",".join(data_utils.asx_sector_yf_static_tickers.keys())
    extract_prompt = extract_prompt.format(SECTORS=sectors_list, RAW_INPUT_DATA=raw_input)
    extract_result = await ai_helper.ai_exec_task("ASX_LISTTINGS_EXTRACT", extract_prompt, "AU")
    if extract_result.is_error:
        raise RuntimeError(
            f"[ASX Listings] LLM failed to generate response for new listing events: {extract_result.error_msg}"
        )

    # Step 3: parse the JSON to result
    default_vals = {
        "currency": "AUD",
        "exchange": "ASX",
        "src": "ASX",
        "link": "https://www.asx.com.au/listings/upcoming-floats-and-listings",
    }

    return models_event.parse_new_listing_events_from_json(extract_result.completion, default_vals)


async def _analyze_asx_listings(events: list[models_event.ListingEvent]) -> list[models_event.ListingEvent]:
    if len(events) == 0:
        return events

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
        companies += f" | MCap: ${conv.number_to_human_format(e.capital or 0, 2)}"
        companies += f" | Sector: {e.sector}"
        companies += f" | Activities: {e.principal_activities}"
        companies += "\n"

    # Step 1: use the low-cost AI model to build a ready-to-execute prompt
    build_prompt = (
        "You are an expert financial analyst and prompt engineer specialising in ASX IPOs and new listings.\n"
        "\n"
        "Your task is to write a detailed, ready-to-execute prompt that instructs a premium AI model\n"
        "to analyze these new ASX listings and predict their price trend.\n"
        "\n"
        "## Companies to analyze\n"
        f"{companies}\n"
        "## Today's date\n"
        f"{now}\n"
        "\n"
        "## Your instructions\n"
        "Write a prompt that instructs the premium model to:\n"
        "\n"
        "1. Use web search to gather data for each company:\n"
        "   - Company prospectus details, business model, and revenue sources\n"
        "   - IPO pricing vs current price (if already listed)\n"
        "   - Sector/peer comparison and market conditions\n"
        "   - Any news, analyst coverage, or institutional interest\n"
        "   - Key risks specific to the company and sector\n"
        "\n"
        "2. For each company, predict price direction at first listing day, first week, first 2 weeks, and first month.\n"
        "\n"
        "3. Output ONLY raw JSON (no markdown/text), with this exact schema:\n"
        "{\n"
        '  "EXCHANGE:SYMBOL": {\n'
        '    "status": "listed|upcoming",\n'
        '    "data_quality": "high|medium|low",\n'
        '    "search_findings": "1-2 sentences: key facts found via search, or \'Insufficient public data found\'",\n'
        '    "stance": "Bullish|Neutral|Bearish|Insufficient Data",\n'
        '    "catalyst": "Primary near-term catalyst or \'None identified\'",\n'
        '    "outlook": {\n'
        '      "d1": { "dir": "↑|↓|→", "reason": "fact-based or state if inferred", "confidence": 0-100 },\n'
        '      "w1": { "dir": "↑|↓|→", "reason": "fact-based or state if inferred", "confidence": 0-100 },\n'
        '      "w2": { "dir": "↑|↓|→", "reason": "fact-based or state if inferred", "confidence": 0-100 },\n'
        '      "m1": { "dir": "↑|↓|→", "reason": "fact-based or state if inferred", "confidence": 0-100 }\n'
        "    },\n"
        '    "risks": ["max 3"]\n'
        "  }\n"
        "}\n"
        "\n"
        '- "d1" is the stock price outlook for the first day the IPO is listed.\n'
        '- "w1" is the first-week outlook, "w2" is the first-2-weeks outlook, and "m1" is the first-month outlook.\n'
        "Make the prompt thorough and specific to each company listed above.\n"
        "The prompt must be self-contained, the premium model will receive it with no other context.\n"
        "The prompt must instruct the premium model to use the hyphen character (-) instead of em-dash (\u2014).\n"
    )

    build_result = await ai_helper.ai_exec_task("ASX_LISTTINGS_BUILD_PROMPT", build_prompt, "AU")
    if build_result.is_error:
        logging.error("[ASX Listings] LLM failed to build analysis prompt: %s", build_result.error_msg)
        return events

    # Step 2: execute the prompt built from previous step using the premium AI model
    analysis_prompt = build_result.completion
    analysis_result = await ai_helper.ai_exec_task("ASX_LISTTINGS_ANALYZE", analysis_prompt, "AU")
    if analysis_result.is_error:
        return events

    # Step 3: parse the JSON and attach analysis to events
    analysis = models_event.parse_listing_analysis_from_json(analysis_result.completion, {})
    for e in events:
        if e.symbol in analysis:
            e.analysis = analysis[e.symbol]

    return events
