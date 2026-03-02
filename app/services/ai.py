import csv
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google import genai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionUserMessageParam
from openai.types.responses import WebSearchPreviewToolParam
from openai.types.responses.web_search_preview_tool_param import UserLocation

from ..models import finhub as models
from ..config import settings
from ..services import crawler as crawler_service

geminiClients: dict[str, genai.Client] = {}
openAIClients: dict[str, AsyncOpenAI] = {}
azureOpenAIClients: dict[str, AsyncOpenAI] = {}

EVENT_INCOMING_EARNINGS = "INCOMING_EARNINGS_EVENTS"
EVENT_INCOMING_DIVIDENDS = "INCOMING_DIVIDEND_EVENTS"
EVENT_ASX_UPCOMING_DIVIDENDS = "ASX_UPCOMING_DIVIDEND_EVENTS"
EVENT_ASX_UPCOMING_EARNINGS = "ASX_UPCOMING_EARNINGS_EVENTS"


def build_prompt_incoming_events(event_type: str, country: str, index: str) -> str:
    country = country.upper() if country else "US"
    tz = (
        "America/New_York"
        if country == "US" or country == "USA" or country == "UNITED STATES" or country == "AMERICA"
        else (
            "Australia/Sydney"
            if country == "AU" or country == "AUS" or country == "AUSTRALIA"
            else "Asia/Ho_Chi_Minh" if country == "VN" or country == "VIETNAM" else "UTC"
        )
    )
    index = (
        index
        if index
        else (
            "Dow Jones 30 Industrial or NASDAQ 100 or NYSE US 100 or S&P 100"
            if country == "US" or country == "USA" or country == "UNITED STATES" or country == "AMERICA"
            else (
                "S&P/ASX 200"
                if country == "AU" or country == "AUS" or country == "AUSTRALIA"
                else "VN100 (HOSE) or HNX30 (HNX)" if country == "VN" or country == "VIETNAM" else "N/A"
            )
        )
    )
    prompt_template = prompts[event_type] if event_type in prompts else ""
    if not prompt_template:
        raise EnvironmentError(f"Prompt template for {event_type} is missing or empty.")
    today = datetime.today()
    prompt = (
        prompt_template.replace("{COUNTRY}", country)
        .replace("{TIMEZONE}", tz)
        .replace("{INDEX}", index)
        .replace("{TODAY}", today.strftime("%Y-%m-%d"))
        .replace("{START_DATE}", today.strftime("%Y-%m-%d"))
        .replace("{END_DATE}", (today + timedelta(days=60)).strftime("%Y-%m-%d"))
    )
    if event_type in prompt_customization and country in prompt_customization[event_type]:
        for placeholder, custom_text in prompt_customization[event_type][country].items():
            lines = [line.strip() for line in custom_text.strip().splitlines() if line.strip()]
            custom_text = "\n".join(lines)
            prompt = prompt.replace(f"{{{placeholder}}}", custom_text)

    if event_type in prompt_customization:
        for placeholder, custom_text in prompt_customization[event_type]["*"].items():
            prompt = prompt.replace(f"{{{placeholder}}}", custom_text)

    return prompt


async def ai_get_incoming_events(event_type: str, prompt: str, country: str) -> models.LLMResponse:
    task_cfg = settings.llm_task_config[event_type] if event_type in settings.llm_task_config else None
    if task_cfg is None:
        raise EnvironmentError(f"LLM task configuration for {event_type} is missing.")

    match task_cfg.vendor.upper():
        case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI":
            start = time.perf_counter()
            client = azureOpenAIClients.get(task_cfg.tier.upper())
            if client is None:
                raise EnvironmentError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
            model = task_cfg.model
            print(
                f"[DEBUG] ai_get_incoming_events({event_type}) "
                f"/ Country: {country} / Vendor: {task_cfg.vendor} / Tier: {task_cfg.tier} / Model: {model}"
            )
            print(prompt)

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
            end = time.perf_counter()
            result = models.LLMResponse(
                completion=response.output_text,
                time_taken_ms=int((end - start) * 1000),
                tokens_prompt=response.usage.input_tokens,
                tokens_completion=response.usage.output_tokens,
                tokens_thought=0,
                is_error=response.output_text == "" or response.status != "completed",
            )

            print(
                f"[DEBUG] ai_get_incoming_events({event_type}) response - Time taken: {result.time_taken_ms} ms, "
                f"Prompt tokens: {result.tokens_prompt}, Completion tokens: {result.tokens_completion}, "
                f"Thought tokens: {result.tokens_thought}, Is error: {result.is_error}"
            )
            print(response.output_text)

            return result
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")


async def ai_get_incoming_earnings_events(country: str, index: str) -> list[models.UpcomingEarningsEvent]:
    """
    Check for incoming earnings events for a market, using AI assistance.

    :param country: Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.).
    :param index: Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.).
    :type country: str
    :return: A list of incoming earnings events for the specified country.
    :rtype: list[models.IncomingEarningsEvent]
    """
    event_type = EVENT_INCOMING_EARNINGS
    prompt = build_prompt_incoming_events(event_type, country, index)
    llm_result = await ai_get_incoming_events(event_type, prompt, country)
    if llm_result.is_error:
        print(f"[ERROR] LLM failed to generate response for incoming earnings events: {llm_result.completion}")
        return []

    # parse response.output_text as JSON array of IncomingEarningsEvent
    try:
        events = models.parse_incoming_earnings_events_from_json(llm_result.completion)
        return events
    except Exception as e:
        print(f"[ERROR] Failed to parse AI response: {e}")
        return []


async def ai_get_incoming_dividends_events(country: str, index: str) -> list[models.UpcomingDividendEvent]:
    """
    Check for incoming dividend/distribution events for a market, using AI assistance.

    :param country: Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.).
    :param index: Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.).
    :type country: str
    :return: A list of incoming dividend/distribution events for the specified country.
    :rtype: list[models.IncomingDividendEvent]
    """
    event_type = EVENT_INCOMING_DIVIDENDS
    prompt = build_prompt_incoming_events(event_type, country, index)
    llm_result = await ai_get_incoming_events(event_type, prompt, country)
    if llm_result.is_error:
        print(
            f"[ERROR] LLM failed to generate response for incoming dividend/distribution events: {llm_result.completion}"
        )
        return []

    # parse response.output_text as JSON array of IncomingDividendEvent
    try:
        events = models.parse_upcoming_dividend_events_from_json(llm_result.completion)
        return events
    except Exception as e:
        print(f"[ERROR] Failed to parse AI response: {e}")
        return []


async def ai_parse_upcoming_events(task_id: str, prompt: str, country: str) -> models.LLMResponse:
    task_cfg = settings.llm_task_config[task_id] if task_id in settings.llm_task_config else None
    if task_cfg is None:
        raise EnvironmentError(f"LLM task configuration for {task_id} is missing.")

    match task_cfg.vendor.upper():
        case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI":
            start = time.perf_counter()
            client = azureOpenAIClients.get(task_cfg.tier.upper())
            if client is None:
                raise EnvironmentError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
            model = task_cfg.model
            print(
                f"[DEBUG] ai_parse_upcoming_events({task_id}) "
                f"/ Country: {country} / Vendor: {task_cfg.vendor} / Tier: {task_cfg.tier} / Model: {model}"
            )
            print(prompt)

            if model.startswith("gpt-5"):
                response = await client.responses.create(
                    model=model,
                    tools=[
                        WebSearchPreviewToolParam(
                            type="web_search_preview",
                            user_location=UserLocation(type="approximate", country=country),
                        ),
                    ],
                    input=prompt,
                )
                end = time.perf_counter()
                result = models.LLMResponse(
                    completion=response.output_text,
                    time_taken_ms=int((end - start) * 1000),
                    tokens_prompt=response.usage.input_tokens,
                    tokens_completion=response.usage.output_tokens,
                    tokens_thought=0,
                    is_error=response.output_text == "" or response.status != "completed",
                )
            else:
                completion = await client.chat.completions.create(
                    model=model,
                    temperature=0.0,
                    messages=[ChatCompletionUserMessageParam(content=prompt, role="user")]
                )
                end = time.perf_counter()
                result = models.LLMResponse(
                    completion=completion.choices[0].message.content if len(completion.choices) > 0 else "",
                    time_taken_ms=int((end - start) * 1000),
                    tokens_prompt=completion.usage.prompt_tokens,
                    tokens_completion=completion.usage.completion_tokens,
                    tokens_thought=0,
                    is_error=len(completion.choices) == 0,
                )

            print(
                f"[DEBUG] ai_get_incoming_events({task_id}) response - Time taken: {result.time_taken_ms} ms, "
                f"Prompt tokens: {result.tokens_prompt}, Completion tokens: {result.tokens_completion}, "
                f"Thought tokens: {result.tokens_thought}, Is error: {result.is_error}"
            )
            print(result.completion)

            return result
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")


async def ai_get_asx_upcoming_dividends_events(index: str = "") -> list[models.UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for ASX, using AI assistance.

    Args:
        index (str): Optional stock index to filter events by (e.g., 'S&P/ASX 200', etc.).
    Returns:
        list[models.UpcomingDividendEvent]: A list of upcoming dividend/distribution events for ASX.
    """
    event_type = EVENT_ASX_UPCOMING_DIVIDENDS
    prompt_template = prompts[event_type] if event_type in prompts else ""
    if not prompt_template:
        raise EnvironmentError(f"Prompt template for {event_type} is missing or empty.")

    tz = ZoneInfo("Australia/Sydney")
    start_date = datetime.now(tz).date()
    end_date = start_date + timedelta(days=14)
    raw_data = crawler_service.scrape_dividends_asx(end_date)
    if raw_data.empty:
        return []

    # optimize tokens:
    # - Removing rows where "Dividend Yield" < 3.00%
    # - Removing column "Url"
    # - If value in column "Dividend Amount" begins with "AU$" or "<AU$", remove the prefix
    if "Dividend Amount" in raw_data.columns:
        raw_data["Dividend Amount"] = raw_data["Dividend Amount"].str.replace(r"^<?AU\$\s*", "", regex=True)
    if "Dividend Yield" in raw_data.columns:
        # remove rows where "Dividend Yield" < 3.00% or not in format of percentage
        raw_data = raw_data[raw_data["Dividend Yield"].str.endswith("%")]
        raw_data = raw_data[raw_data["Dividend Yield"].str.rstrip("%").astype(float) >= 3.00]
    if "Url" in raw_data.columns:
        raw_data = raw_data.drop(columns=["Url"])

    prompt = prompt_template.replace("{RAW_INPUT_DATA}", raw_data.to_csv(index=False, quoting=csv.QUOTE_NONNUMERIC))
    if index:
        prompt = (
            prompt
            .replace("{ROLE}", f"with live web search capability")
            .replace("{OBJECTIVE}", f"Also, filter for companies that are CURRENT constituents of the {index} index.")
            .replace("{VALIDATION_RULES}", f"MUST verify {index} membership using the most recent official constituent list.")
            .replace("{PROCESS}",f"INDEX FILTERING INSTRUCTIONS (CRITICAL)\n- Use your web search to find an up-to-date list of current {index} constituents (e.g., from MarketIndex or standard financial portals).\n-Filter the CSV input. DO NOT include any company in the final output unless it is confirmed to be in the {index}.\n-Do NOT search for the dividend events themselves online. Only search to verify index membership. Use the dividend data exactly as provided in the CSV.")
        )
    else:
        prompt = (
            prompt
            .replace("{ROLE}", "")
            .replace("{OBJECTIVE}", "")
            .replace("{VALIDATION_RULES}", "")
            .replace("{PROCESS}", "")
        )

    if not index:
        llm_result = await ai_parse_upcoming_events("PARSE_UPCOMING_DIVIDEND_EVENTS_NO_WEB_SEARCH", prompt, "AU")
    else:
        llm_result = await ai_parse_upcoming_events("PARSE_UPCOMING_DIVIDEND_EVENTS_WEB_SEARCH", prompt, "AU")

    if llm_result.is_error:
        raise RuntimeError(f"[ERROR] LLM failed to generate response for upcoming dividend/distribution events: {llm_result.completion}")

    default_vals = {
        "src": "ASX",
        "currency": "AUD",
        "status": "declared",
    }
    events = models.parse_upcoming_dividend_events_from_json(llm_result.completion, default_vals)
    return events


async def ai_get_asx_upcoming_earnings_events(index: str = "") -> list[models.UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events for ASX, using AI assistance.

    Args:
        index (str): Optional stock index to filter events by (e.g., 'S&P/ASX 200', etc.).
    Returns:
        list[models.UpcomingEarningsEvent]: A list of upcoming earnings events for ASX.
    """
    event_type = EVENT_ASX_UPCOMING_EARNINGS
    prompt_template = prompts[event_type] if event_type in prompts else ""
    if not prompt_template:
        raise EnvironmentError(f"Prompt template for {event_type} is missing or empty.")

    tz = ZoneInfo("Australia/Sydney")
    start_date = datetime.now(tz).date()
    end_date = start_date + timedelta(days=7)
    raw_data = crawler_service.scrape_earnings_asx(end_date)
    if raw_data.empty:
        return []

    # optimize tokens:
    # - Removing column "Url"
    if "Url" in raw_data.columns:
        raw_data = raw_data.drop(columns=["Url"])

    prompt = prompt_template.replace("{RAW_INPUT_DATA}", raw_data.to_csv(index=False, quoting=csv.QUOTE_NONNUMERIC))
    if index:
        prompt = (
            prompt
            .replace("{ROLE}", f"with live web search capability")
            .replace("{OBJECTIVE}", f"Also, filter for companies that are CURRENT constituents of the {index} index.")
            .replace("{VALIDATION_RULES}", f"MUST verify {index} membership using the most recent official constituent list.")
            .replace("{PROCESS}",f"INDEX FILTERING INSTRUCTIONS (CRITICAL)\n- Use your web search to find an up-to-date list of current {index} constituents (e.g., from MarketIndex or standard financial portals).\n-Filter the CSV input. DO NOT include any company in the final output unless it is confirmed to be in the {index}.\n-Do NOT search for the earnings/financial events themselves online. Only search to verify index membership. Use the earnings data exactly as provided in the CSV.")
        )
    else:
        prompt = (
            prompt
            .replace("{ROLE}", "")
            .replace("{OBJECTIVE}", "")
            .replace("{VALIDATION_RULES}", "")
            .replace("{PROCESS}", "")
        )

    if not index:
        llm_result = await ai_parse_upcoming_events("PARSE_UPCOMING_EARNINGS_EVENTS_NO_WEB_SEARCH", prompt, "AU")
    else:
        llm_result = await ai_parse_upcoming_events("PARSE_UPCOMING_EARNINGS_EVENTS_WEB_SEARCH", prompt, "AU")

    if llm_result.is_error:
        raise RuntimeError(f"[ERROR] LLM failed to generate response for upcoming earnings events: {llm_result.completion}")

    default_vals = {
        "src": "ASX",
        "status": "estimated",
        "report_period": "N/A",
    }
    events = models.parse_upcoming_earnings_events_from_json(llm_result.completion, default_vals)
    return events

prompts: dict[str, str] = {}

prompt_customization = {
    EVENT_INCOMING_EARNINGS: {
        "VN": {
            "CUSTOM_KEYWORDS": """
                Vietnamese search keywords to use:
                - "Lịch công bố BCTC"
                - "Lịch sự kiện chứng khoán"
                - "Báo cáo tài chính" (BCTC)
                - "Kết quả kinh doanh" (KQKD)
                """,
            "OFFICIAL_INDEX_PROVIDERS": "HOSE or HNX",
            "REPORT_PERIOD_MAPPINGS": """
                # REPORT_PERIOD CLASSIFICATION

                Map as:
                - Quarterly (Q1/Q2/Q3/Q4, quý)
                - Half-year (6T, H1, bán niên)
                - Full-year (annual, year-end)
                - Interim (explicitly stated interim but not quarterly/half-year/full-year)
                """,
            "CUSTOM_SEARCH": (
                "Additional Vietnamese financial news websites can be used for cross-referencing and validation, such as: "
                "vietstock.vn, vietnamfinance.vn, vietnambiz.vn, vnfinance.vn, thoibaotaichinhvietnam.vn, "
                "vietnambusinessinsider.vn, and cafef.vn."
            ),
            "SOURCES": "HOSE, HNX, Vietstock, CafeF, VNFinance, VietnamBusinessInsider, etc.",
            "BROADER_SEARCH": """ "Lịch công bố báo cáo tài chính" or "Lịch sự kiện chứng khoán" """,
        },
        "AU": {
            "OFFICIAL_INDEX_PROVIDERS": "ASX",
            "SOURCES": "Market Index, CommSec, Bloomberg, Reuters, Yahoo Finance, etc.",
            "BROADER_SEARCH": """ "Australian earnings calendars" or "ASX reporting season dates" """,
        },
        "*": {
            "CUSTOM_KEYWORDS": "",
            "OFFICIAL_INDEX_PROVIDERS": "",
            "REPORT_PERIOD_MAPPINGS": "",
            "CUSTOM_SEARCH": "",
            "SOURCES": "Bloomberg, Reuters, MarketScreener, Yahoo Finance, etc.",
            "BROADER_SEARCH": """ "Earnings calendar" or "Earnings season dates" """,
        },
    },
    EVENT_INCOMING_DIVIDENDS: {
        "VN": {
            "CUSTOM_KEYWORDS": """
                Vietnamese search keywords to use:
                - "Lịch công bố chia cổ tức"
                - "Lịch công bố trả cổ tức"
                - "Trả cổ tức bằng tiền mặt"
                - "Trả cổ tức bằng cổ phiếu"
                - "Ngày giao dịch không hưởng quyền"
                """,
            "OFFICIAL_INDEX_PROVIDERS": "HOSE or HNX",
            "CUSTOM_SEARCH": (
                "Additional Vietnamese financial news websites can be used for cross-referencing and validation, such as: "
                "vietstock.vn, vietnamfinance.vn, vietnambiz.vn, vnfinance.vn, thoibaotaichinhvietnam.vn, "
                "vietnambusinessinsider.vn, and cafef.vn."
            ),
            "SOURCES": "HOSE, HNX, Vietstock, CafeF, VNFinance, VietnamBusinessInsider, etc.",
            "BROADER_SEARCH": """ "Lịch công bố chia cổ tức" or "Lịch công bố trả cổ tức" """,
        },
        "AU": {
            "OFFICIAL_INDEX_PROVIDERS": "ASX",
            "SOURCES": "Market Index, CommSec, Bloomberg, Reuters, Yahoo Finance, etc.",
            "BROADER_SEARCH": """ "Australian ex-dividend calendars" """,
        },
        "*": {
            "CUSTOM_KEYWORDS": "",
            "OFFICIAL_INDEX_PROVIDERS": "",
            "CUSTOM_SEARCH": "",
            "SOURCES": "Bloomberg, Reuters, MarketScreener, Yahoo Finance, etc.",
            "BROADER_SEARCH": """ "Ex-dividend calendar" """,
        },
    },
}
