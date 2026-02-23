from datetime import datetime

from google import genai
from openai import AsyncOpenAI
from openai.types.responses import WebSearchPreviewToolParam
from openai.types.responses.web_search_preview_tool_param import UserLocation

from ..models import finhub as models
from ..config import settings

geminiClients: dict[str, genai.Client] = {}
openAIClients: dict[str, AsyncOpenAI] = {}
azureOpenAIClients: dict[str, AsyncOpenAI] = {}


async def ai_get_incoming_earnings_events(country: str, index: str) -> list[models.IncomingEarningsEvent]:
    """
    Check for incoming earnings events for a market, using AI assistance.

    :param country: Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.).
    :param index: Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.).
    :type country: str
    :return: A list of incoming earnings events for the specified country.
    :rtype: list[models.IncomingEarningsEvent]
    """
    country = country.upper() if country else "US"
    tz = (
        "America/New_York"
        if country == "US"
        else "Australia/Sydney" if country == "AU" else "Asia/Ho_Chi_Minh" if country == "VN" else "UTC"
    )
    index = (
        index.upper()
        if index
        else (
            "Dow Jones 30 Industrial or NASDAQ 100 or NYSE US 100 or S&P 100"
            if country == "US"
            else "S&P/ASX 200" if country == "AU" else "VN100 or HNX30" if country == "VN" else "N/A"
        )
    )
    prompt = (
        prompt_get_incoming_earnings_events.replace("{TIMEZONE}", tz)
        .replace("{INDEX}", index)
        .replace("{TODAY}", datetime.today().strftime("%Y-%m-%d"))
    )

    task_cfg = (
        settings.llm_task_config["INCOMING_EARNINGS_EVENTS"]
        if "INCOMING_EARNINGS_EVENTS" in settings.llm_task_config
        else None
    )
    if task_cfg is None:
        raise EnvironmentError("LLM task configuration for INCOMING_EARNINGS_EVENTS is missing.")

    match task_cfg.vendor.upper():
        case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI":
            client = azureOpenAIClients.get(task_cfg.tier.upper())
            if client is None:
                raise EnvironmentError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
            model = task_cfg.model
            print(
                f"[DEBUG] ai_get_incoming_earnings_event / Country: {country} / Index: {index} / Vendor: {task_cfg.vendor} / Tier: {task_cfg.tier} / Model: {model}\n",
                prompt,
            )
            temperature = None if model.startswith("gpt-5") else 0.0
            response = await client.responses.create(
                model=model,
                temperature=temperature,
                tools=[
                    WebSearchPreviewToolParam(
                        type="web_search_preview",
                        user_location=UserLocation(type="approximate", country=country),
                    ),
                ],
                input=prompt,
            )
            print("[DEBUG] ai_get_incoming_earnings_event response:\n", response.output_text)

            # parse response.output_text as JSON array of IncomingEarningsEvent
            try:
                events = models.parse_incoming_earnings_events_from_json(response.output_text)
                return events
            except Exception as e:
                print(f"[ERROR] Failed to parse AI response: {e}")
                return []
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")


async def ai_get_incoming_dividends_events(country: str, index: str) -> list[models.IncomingDividendEvent]:
    """
    Check for incoming dividend/distribution events for a market, using AI assistance.

    :param country: Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.).
    :param index: Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.).
    :type country: str
    :return: A list of incoming dividend/distribution events for the specified country.
    :rtype: list[models.IncomingDividendEvent]
    """
    country = country.upper() if country else "US"
    tz = (
        "America/New_York"
        if country == "US"
        else "Australia/Sydney" if country == "AU" else "Asia/Ho_Chi_Minh" if country == "VN" else "UTC"
    )
    index = (
        index.upper()
        if index
        else (
            "Dow Jones 30 Industrial or NASDAQ 100 or NYSE US 100 or S&P 100"
            if country == "US"
            else "S&P/ASX 200" if country == "AU" else "VN100 or HNX30" if country == "VN" else "N/A"
        )
    )
    prompt = (
        prompt_get_incoming_dividend_distribution_events.replace("{TIMEZONE}", tz)
        .replace("{INDEX}", index)
        .replace("{TODAY}", datetime.today().strftime("%Y-%m-%d"))
    )

    task_cfg = (
        settings.llm_task_config["INCOMING_DIVIDEND_EVENTS"]
        if "INCOMING_DIVIDEND_EVENTS" in settings.llm_task_config
        else None
    )
    if task_cfg is None:
        raise EnvironmentError("LLM task configuration for INCOMING_DIVIDEND_EVENTS is missing.")

    match task_cfg.vendor.upper():
        case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI":
            client = azureOpenAIClients.get(task_cfg.tier.upper())
            if client is None:
                raise EnvironmentError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
            model = task_cfg.model
            print(
                f"[DEBUG] ai_get_incoming_dividends_events / Country: {country} / Index: {index} / Vendor: {task_cfg.vendor} / Tier: {task_cfg.tier} / Model: {model}\n",
                prompt,
            )
            temperature = None if model.startswith("gpt-5") else 0.0
            response = await client.responses.create(
                model=model,
                temperature=temperature,
                tools=[
                    WebSearchPreviewToolParam(
                        type="web_search_preview",
                        user_location=UserLocation(type="approximate", country=country),
                    ),
                ],
                input=prompt,
            )
            print("[DEBUG] ai_get_incoming_dividends_events response:\n", response.output_text)

            # parse response.output_text as JSON array of IncomingDividendEvent
            try:
                events = models.parse_incoming_dividend_events_from_json(response.output_text)
                return events
            except Exception as e:
                print(f"[ERROR] Failed to parse AI response: {e}")
                return []
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")


prompt_get_incoming_earnings_events = """
# ROLE

You are a financial research assistant with live web search capability.

# TIME REFERENCE

- Use {TIMEZONE} timezone.
- Define TODAY as {TODAY} in that timezone.
- Explicitly determine:
  START_DATE = TODAY (inclusive)
  END_DATE = TODAY + 28 calendar days (inclusive)
- Only include events where:
  START_DATE <= earnings_date <= END_DATE
- Earnings date must be strictly in the FUTURE relative to TODAY.

# OBJECTIVE

Find 10-20 companies that are CURRENT constituents of the {INDEX} index
AND have an upcoming earnings or financial results announcement within the defined 28-day window.

# DEFINITION OF EARNINGS

Valid events include:
- Quarterly results
- Half-year results
- Full-year results
- Official interim results
- Official financial statement release dates

Do NOT include:
- AGM notices
- Dividend announcements only
- Trading updates without financial results
- Past results
- Month-only or week-only expected timing

# REQUIRED VALIDATION

1. You MUST use live web search.
2. You SHOULD verify current index membership using:
   - Official index provider publication
3. Earnings date must be confirmed by:
   - Company investor relations page
   - Official exchange announcement
   - Official exchange filing document
   - Reputable financial data provider (Bloomberg, Reuters, MarketScreener, Yahoo Finance, Vietstock, etc.)
4. The earnings date must:
   - Be explicitly stated (no inference)
   - Fall within the 28-day window
   - Be converted to ISO format: yyyy-MM-dd
5. If the date is not officially confirmed but appears as an estimate
   from a reputable financial data provider,
   mark status as "estimated".
6. If fewer than 10 qualifying companies are found,
   return all that qualify.

# DATA FIELDS

For each company return:

- symbol
- company_name
- date (yyyy-MM-dd)
- report_period (quarterly | half-year | full-year | interim)
- status (confirmed | estimated)
- source_name
- link (direct URL to specific page confirming the date)

Reject entries if:
- Membership cannot be verified
- Date is outside window
- Source is unclear
- Link is generic homepage

# OUTPUT FORMAT (STRICT)

Return ONLY valid JSON.
No markdown.
No explanation.
No comments.
No trailing commas.

Structure:

[
  {
    "symbol": "TICKER",
    "company_name": "Company Name",
    "date": "yyyy-MM-dd",
    "report_period": "quarterly",
    "status": "confirmed",
    "source_name": "ASX | HOSE | NASDAQ | etc",
    "link": "https://exact-source-url"
  }
]

# PROCESS

Step 1: Retrieve current {INDEX} constituents from official sources.
Step 2: Compute date window using {TIMEZONE} timezone.
Step 3: Search for upcoming earnings announcements.
Step 4: Validate each candidate against:
        - Index membership
        - Date window
        - Source credibility
Step 5: Return 10–20 validated results in strict JSON.

Begin.
"""

prompt_get_incoming_dividend_distribution_events = """
# ROLE

You are a financial research assistant with live web search capability.

# TIME REFERENCE

- Use {TIMEZONE} timezone.
- Define TODAY as {TODAY} in that timezone.
- Explicitly determine:
  START_DATE = TODAY (inclusive)
  END_DATE = TODAY + 28 calendar days (inclusive)
- Only include events where:
  START_DATE <= dividend_date <= END_DATE
- Dividend/distribution date must be strictly in the FUTURE relative to TODAY.

# OBJECTIVE

Find 10-20 companies that are CURRENT constituents of the {INDEX} index
AND have an upcoming dividend or distribution-related event within the defined 28-day window.

# DEFINITION OF VALID DIVIDEND EVENTS

Valid events include:
- Ex-dividend date
- Ex-distribution date
- Record date
- Payment date
- Distribution payment date (for REITs, ETFs, trusts)
- Special dividend payment date
- Interim dividend payment date
- Final dividend payment date

Do NOT include:
- Historical dividend dates
- Dividend announcement date only (without a confirmed ex-date or payment date)
- Month-only or week-only timing estimates
- Dividend reinvestment plan (DRP) notice unless a payment/ex-date is specified
- Earnings results that merely mention dividends

# REQUIRED VALIDATION

1. You MUST use live web search.
2. You SHOULD verify current index membership using:
   - Official index provider publication
3. Dividend/distribution date must be confirmed by at least one of:
   - Company investor relations page
   - Official ASX announcement
   - Official exchange filing
   - Reputable financial data provider (Bloomberg, Reuters, MarketScreener, Yahoo Finance, Vietstock, etc.)
4. The dividend date must:
   - Be explicitly stated (no inference)
   - Fall within the 28-day window
   - Be converted to ISO format: yyyy-MM-dd
5. If the date is not officially confirmed but appears as an estimate
   from a reputable financial data provider,
   mark status as "estimated".
6. If fewer than 10 qualifying companies are found,
   return all that qualify.

# DATA FIELDS

For each company return:

- symbol
- company_name
- date (yyyy-MM-dd)
- event_type (ex-dividend | record | payment | distribution | special)
- status (confirmed | estimated)
- dividend/distribution value
- currency
- source_name
- link (direct URL to specific page confirming the date)

Reject entries if:
- Date is outside window
- Source is unclear or non-authoritative
- Link is generic homepage
- Date is only implied but not explicitly stated

OUTPUT FORMAT (STRICT)

Return ONLY valid JSON.
No markdown.
No explanation.
No comments.
No trailing commas.

Structure:

[
  {
    "symbol": "TICKER",
    "company_name": "Company Name",
    "date": "yyyy-MM-dd",
    "event_type": "ex-dividend",
    "status": "confirmed",
    "value": 100,
    "currency": "AUD | USD | VND | etc",
    "source_name": "ASX | S&P Dow Jones | Bloomberg | etc",
    "link": "https://exact-source-url"
  }
]

PROCESS

Step 1: Retrieve current {INDEX} constituents from official sources.
Step 2: Compute date window using {TIMEZONE} timezone.
Step 3: Search for upcoming dividend/distribution events.
Step 4: Validate each candidate against:
        - Index membership
        - Date window
        - Source credibility
Step 5: Return 10–20 validated results in strict JSON.

Begin.
"""
