import asyncio
import logging
import os
import random
import time
import weakref
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import openai
from pydantic import BaseModel, Field, ValidationError

from .. import config

# ----------------------------------------------------------------------#


class LLMRateLimitError(RuntimeError):
    """An OpenAI-compatible provider remained rate limited beyond the retry budget."""


class LLMResponse(BaseModel):
    """
    Normalized result returned by an AI provider.

    Attributes:
        is_error: Whether the provider request completed successfully.
        completion: Generated response text. Empty when the request fails.
        error_msg: Error message for a failed request. Empty on success.
        time_taken_ms: Time taken to complete the request in milliseconds.
        tokens_prompt: Number of input or prompt tokens reported by the provider.
        tokens_completion: Number of generated tokens reported by the provider.
        tokens_thought: Number of thought or reasoning tokens reported by the provider.
        tokens_tool: Number of tool usage tokens reported by the provider.
        tokens_cache: Number of cached tokens reported by the provider.
        tokens_total: Total tokens reported by the provider.
        citation_urls: Provider-issued URL citations attached to the generated response.
    """

    is_error: bool = False
    error_msg: str | None = None
    completion: str = ""
    time_taken_ms: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_thought: int = 0
    tokens_tool: int = 0
    tokens_cache: int = 0
    tokens_total: int = 0
    citation_urls: list[str] = Field(default_factory=list)


def log_structured_validation_failure(
    feature: str,
    stage: str,
    error: Exception,
) -> None:
    """Log structured-output validation details without including rejected input values."""

    if isinstance(error, ValidationError):
        errors = error.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )
        details = []
        for item in errors[:8]:
            location = ".".join(str(part) for part in item["loc"]) or "<root>"
            details.append(f"{location}: {item['msg']} [{item['type']}]")
        if len(errors) > len(details):
            details.append(f"{len(errors) - len(details)} additional error(s)")
        summary = "; ".join(details)
    else:
        summary = str(error)

    logging.warning(
        "[%s] %s structured-output validation failed: %s",
        feature,
        stage,
        summary[:2000],
    )


def _is_debug_mode() -> bool:
    return os.getenv("LLM_DEBUG_MODE", "").lower() in ("1", "true", "yes")


def _extract_url_citations(response: object) -> list[str]:
    output = getattr(response, "output", None)
    if output is None:
        return []

    citation_urls: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, BaseModel):
            collect(value.model_dump(mode="python"))
            return
        if isinstance(value, Mapping):
            if value.get("type") == "url_citation" and isinstance(value.get("url"), str):
                citation_urls.append(value["url"])
            for nested_value in value.values():
                collect(nested_value)
            return
        if isinstance(value, list | tuple):
            for nested_value in value:
                collect(nested_value)
            return
        if hasattr(value, "__dict__"):
            collect(vars(value))

    collect(output)
    return list(dict.fromkeys(citation_urls))


_OPENAI_SUPPORTED_STRING_FORMATS = frozenset(
    {
        "date-time",
        "time",
        "date",
        "duration",
        "email",
        "hostname",
        "ipv4",
        "ipv6",
        "uuid",
    }
)


def _openai_compatible_json_schema(schema: Mapping[str, object]) -> dict[str, object]:
    if "$ref" in schema:
        return {"$ref": schema["$ref"]}
    return {
        key: _openai_compatible_json_schema_value(value)
        for key, value in schema.items()
        if not (key == "format" and isinstance(value, str) and value not in _OPENAI_SUPPORTED_STRING_FORMATS)
    }


def _openai_compatible_json_schema_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _openai_compatible_json_schema(value)
    if isinstance(value, list | tuple):
        return [_openai_compatible_json_schema_value(item) for item in value]
    return value


# ----------------------------------------------------------------------#


async def ai_exec_task(
    task_id: str,
    prompt: str,
    *,
    country: str = "",
    response_json_schema: Mapping[str, object] | None = None,
    schema_name: str = "json_responses",
) -> LLMResponse:
    """
    Executes a task using the appropriate LLM based on the task configuration.
    """
    task_cfg = config.settings_llm_task.tasks.get(task_id)
    if not task_cfg:
        raise ValueError(f"LLM task configuration for task_id '{task_id}' not found.")
    return await ai_exec_prompt(
        task_cfg,
        prompt,
        country=country,
        response_json_schema=response_json_schema,
        schema_name=schema_name,
    )


async def ai_exec_prompt(
    task_cfg: config.LLMTaskConfig,
    prompt: str,
    *,
    country: str = "",
    response_json_schema: Mapping[str, object] | None = None,
    schema_name: str = "json_responses",
) -> LLMResponse:
    """
    Executes a prompt using the specified LLM task configuration.
    """
    used_vendor = task_cfg.vendor.upper()
    match used_vendor:
        case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI" | "AZURE-OPENAI":
            return await _exec_prompt_azure_openai(
                task_cfg,
                prompt,
                country=country,
                response_json_schema=response_json_schema,
                schema_name=schema_name,
            )
        case "OPENAI":
            return await _exec_prompt_openai(
                task_cfg,
                prompt,
                country=country,
                response_json_schema=response_json_schema,
                schema_name=schema_name,
            )
        case "OPENROUTER" | "OPEN ROUTER" | "OPEN_ROUTER" | "OPEN-ROUTER":
            return await _exec_prompt_openrouter(
                task_cfg,
                prompt,
                country=country,
                response_json_schema=response_json_schema,
                schema_name=schema_name,
            )
        case "GEMINI":
            return await _exec_prompt_gemini(
                task_cfg,
                prompt,
                response_json_schema=response_json_schema,
            )
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")


async def _exec_prompt_azure_openai(
    task_cfg: config.LLMTaskConfig,
    prompt: str,
    *,
    country: str = "",
    response_json_schema: Mapping[str, object] | None = None,
    schema_name: str,
) -> LLMResponse:
    """
    Execute a prompt using Azure OpenAI and return the response.
    """
    client = config.settings_llm_vendor.get_llm_client("AZURE_OPENAI", task_cfg.tier)
    if client is None:
        raise OSError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await _exec_prompt_openai_client(
        client,
        task_cfg,
        prompt,
        country=country,
        response_json_schema=response_json_schema,
        schema_name=schema_name,
    )


async def _exec_prompt_openrouter(
    task_cfg: config.LLMTaskConfig,
    prompt: str,
    *,
    country: str = "",
    response_json_schema: Mapping[str, object] | None = None,
    schema_name: str,
) -> LLMResponse:
    """
    Execute a prompt using OpenRouter and return the response.
    """
    client = config.settings_llm_vendor.get_llm_client("OPEN_ROUTER", task_cfg.tier)
    if client is None:
        raise OSError(f"OpenRouter client for tier '{task_cfg.tier}' is not configured.")
    return await _exec_prompt_openai_client(
        client,
        task_cfg,
        prompt,
        is_openrouter=True,
        country=country,
        response_json_schema=response_json_schema,
        schema_name=schema_name,
    )


async def _exec_prompt_openai(
    task_cfg: config.LLMTaskConfig,
    prompt: str,
    *,
    country: str = "",
    response_json_schema: Mapping[str, object] | None = None,
    schema_name: str,
) -> LLMResponse:
    """
    Execute a prompt using OpenAI and return the response.
    """
    client = config.settings_llm_vendor.get_llm_client("OPENAI", task_cfg.tier)
    if client is None:
        raise OSError(f"OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await _exec_prompt_openai_client(
        client,
        task_cfg,
        prompt,
        country=country,
        response_json_schema=response_json_schema,
        schema_name=schema_name,
    )


_MAX_TOOL_CALLS_BY_REASONING: dict[config.ReasoningEffort | None, int] = {
    None: 7,
    "Low": 4,
    "Medium": 7,
    "High": 13,
}

_SEARCH_CONTEXT_SIZE_BY_REASONING: dict[config.ReasoningEffort | None, str] = {
    None: "medium",
    "Low": "low",
    "Medium": "medium",
    "High": "high",
}

_NON_RETRYABLE_RATE_LIMIT_CODES = frozenset(
    {
        "billing_hard_limit_reached",
        "insufficient_quota",
        "quota_exceeded",
    }
)
_OPENAI_LIMITERS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    dict[tuple[str, str, str], asyncio.Semaphore],
] = weakref.WeakKeyDictionary()


def _openai_provider_name(vendor: str) -> str:
    normalized = vendor.upper().replace("-", "").replace("_", "").replace(" ", "")
    if normalized == "AZUREOPENAI":
        return "AZURE_OPENAI"
    if normalized == "OPENROUTER":
        return "OPEN_ROUTER"
    return normalized


def _openai_limiter(task_cfg: config.LLMTaskConfig) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    loop_limiters = _OPENAI_LIMITERS.setdefault(loop, {})
    key = (
        _openai_provider_name(task_cfg.vendor),
        task_cfg.tier.upper(),
        task_cfg.model,
    )
    limiter = loop_limiters.get(key)
    if limiter is None:
        limiter = asyncio.Semaphore(config.settings_openai_execution.max_concurrent_requests)
        loop_limiters[key] = limiter
    return limiter


def _rate_limit_error_code(exc: openai.RateLimitError) -> str | None:
    if not isinstance(exc.body, Mapping):
        return None
    error = exc.body.get("error")
    if isinstance(error, Mapping):
        code = error.get("code") or error.get("type")
    else:
        code = exc.body.get("code") or exc.body.get("type")
    return code.lower() if isinstance(code, str) else None


def _is_retryable_rate_limit(exc: openai.RateLimitError) -> bool:
    return _rate_limit_error_code(exc) not in _NON_RETRYABLE_RATE_LIMIT_CODES


def _parse_retry_after(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at - datetime.now(UTC)).total_seconds()
    return max(0.0, seconds)


def _provider_retry_delay(exc: openai.RateLimitError) -> float | None:
    headers = exc.response.headers
    for header_name in ("retry-after-ms", "x-ms-retry-after-ms"):
        value = headers.get(header_name)
        if value is None:
            continue
        try:
            return max(0.0, float(value) / 1000)
        except ValueError:
            continue
    retry_after = headers.get("retry-after")
    return _parse_retry_after(retry_after) if retry_after is not None else None


def _fallback_retry_delay(retry_count: int) -> float:
    settings = config.settings_openai_execution
    delay_cap = min(
        settings.rate_limit_max_backoff_seconds,
        settings.rate_limit_initial_backoff_seconds * (2 ** min(retry_count, 30)),
    )
    return random.uniform(0, delay_cap)


async def _execute_openai_request(
    client: openai.AsyncOpenAI,
    task_cfg: config.LLMTaskConfig,
    request_kwargs: dict[str, object],
    *,
    is_openrouter: bool,
) -> object:
    started_at = time.monotonic()
    retry_count = 0

    while True:
        try:
            async with _openai_limiter(task_cfg):
                if is_openrouter:
                    return await client.chat.completions.create(**request_kwargs)
                return await client.responses.create(**request_kwargs)
        except openai.RateLimitError as exc:
            if not _is_retryable_rate_limit(exc):
                raise

            elapsed = time.monotonic() - started_at
            remaining = config.settings_openai_execution.rate_limit_max_wait_seconds - elapsed
            delay = _provider_retry_delay(exc)
            if delay is None:
                delay = _fallback_retry_delay(retry_count)
            if remaining <= 0 or delay > remaining:
                raise LLMRateLimitError(
                    f"{_openai_provider_name(task_cfg.vendor)} model '{task_cfg.model}' "
                    f"remained rate limited for {elapsed:.1f} seconds."
                ) from exc

            retry_count += 1
            logging.warning(
                "_exec_prompt_openai_client('%s') - Rate limited by {%s - %s - %s}; "
                "retrying in %.2f seconds (retry %d).",
                task_cfg.task_name,
                task_cfg.vendor,
                task_cfg.tier,
                task_cfg.model,
                delay,
                retry_count,
            )
            await asyncio.sleep(delay)


async def _exec_prompt_openai_client(
    client: openai.AsyncOpenAI,
    task_cfg: config.LLMTaskConfig,
    prompt: str,
    *,
    is_openrouter: bool = False,
    country: str = "",
    response_json_schema: Mapping[str, object] | None = None,
    schema_name: str,
) -> LLMResponse:
    """
    Execute a prompt using OpenAI client and return the response.
    """
    model = task_cfg.model
    reasoning_effort = task_cfg.reasoning_effort
    use_web_search = task_cfg.use_web_search
    max_tool_calls = (
        task_cfg.max_tool_calls if task_cfg.max_tool_calls > 0 else _MAX_TOOL_CALLS_BY_REASONING[reasoning_effort]
    )
    timer_start = time.perf_counter()
    logging.info(
        "_exec_prompt_openai_client('%s') - Using {%s - %s - %s} | Web search: %s | Reasoning: %s "
        "| Max tool calls: %d | Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
        task_cfg.use_web_search,
        task_cfg.reasoning_effort,
        max_tool_calls,
    )
    print(prompt if _is_debug_mode() else "<prompt omitted>")

    openai_json_schema = (
        _openai_compatible_json_schema(response_json_schema) if response_json_schema is not None else None
    )

    if is_openrouter:
        request_kwargs: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        extra_body: dict[str, object] = {}
        if use_web_search:
            extra_body["plugins"] = [{"id": "web"}]
        if reasoning_effort is not None:
            extra_body["reasoning"] = {"effort": reasoning_effort.lower()}
        if extra_body:
            request_kwargs["extra_body"] = extra_body
        if openai_json_schema is not None:
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": openai_json_schema,
                },
            }
    else:
        request_kwargs: dict[str, object] = {
            "model": model,
            "input": prompt,
        }
        if use_web_search:
            request_kwargs["max_tool_calls"] = max_tool_calls
            request_kwargs["tools"] = [
                {
                    "type": "web_search",
                    "search_context_size": _SEARCH_CONTEXT_SIZE_BY_REASONING[reasoning_effort],
                    "user_location": {
                        "type": "approximate",
                        "country": country,
                    }
                    if country
                    else None,
                }
            ]
        if reasoning_effort is not None:
            request_kwargs["reasoning"] = {"effort": reasoning_effort.lower()}
        if openai_json_schema is not None:
            request_kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": openai_json_schema,
                }
            }
    ai_resp = await _execute_openai_request(
        client,
        task_cfg,
        request_kwargs,
        is_openrouter=is_openrouter,
    )

    timer_end = time.perf_counter()
    token_usage_input = 0
    token_usage_output = 0
    token_usage_thought = 0
    token_usage_tool = 0
    token_usage_cache = 0
    token_usage_total = 0
    completion = ""
    citation_urls: list[str] = []

    if is_openrouter:
        from openai.types.chat import ChatCompletion

        chat_resp: ChatCompletion = ai_resp
        is_error = (not chat_resp.choices) or (not chat_resp.choices[0].message)
        if chat_resp.choices and chat_resp.choices[0].message:
            completion = chat_resp.choices[0].message.content or ""
        if chat_resp.usage:
            token_usage_input = chat_resp.usage.prompt_tokens or 0
            token_usage_output = chat_resp.usage.completion_tokens or 0
            token_usage_thought = (
                chat_resp.usage.completion_tokens_details.reasoning_tokens or 0
                if chat_resp.usage.completion_tokens_details
                else 0
            )
            token_usage_cache = (
                chat_resp.usage.prompt_tokens_details.cached_tokens or 0 if chat_resp.usage.prompt_tokens_details else 0
            )
            token_usage_total = chat_resp.usage.total_tokens or 0
    else:
        from openai.types.responses import Response

        response_resp: Response = ai_resp
        is_error = str(response_resp.status).lower() != "completed"
        completion = response_resp.output_text or ""
        citation_urls = _extract_url_citations(response_resp)
        if response_resp.usage:
            token_usage_input = response_resp.usage.input_tokens or 0
            token_usage_output = response_resp.usage.output_tokens or 0
            token_usage_thought = (
                response_resp.usage.output_tokens_details.reasoning_tokens or 0
                if response_resp.usage.output_tokens_details
                else 0
            )
            token_usage_cache = (
                response_resp.usage.input_tokens_details.cached_tokens or 0
                if response_resp.usage.input_tokens_details
                else 0
            )
            token_usage_total = response_resp.usage.total_tokens or 0

    result = LLMResponse(
        is_error=is_error,
        completion=completion,
        time_taken_ms=int((timer_end - timer_start) * 1000),
        tokens_prompt=token_usage_input,
        tokens_completion=token_usage_output,
        tokens_thought=token_usage_thought,
        tokens_tool=token_usage_tool,
        tokens_cache=token_usage_cache,
        tokens_total=token_usage_total,
        citation_urls=citation_urls,
    )

    logging.info(
        "_exec_prompt_openai_client('%s') - Time taken: %d ms | Tokens used: {prompt: %d, completion: %d, thought: %d, tool: %d, cache: %d, total: %d} | Is error: %s | Response:",
        task_cfg.task_name,
        result.time_taken_ms,
        result.tokens_prompt,
        result.tokens_completion,
        result.tokens_thought,
        result.tokens_tool,
        result.tokens_cache,
        result.tokens_total,
        result.is_error,
    )
    if result.is_error:
        result.error_msg = result.completion
    print(result.completion if _is_debug_mode() else "<response omitted>")

    return result


async def _exec_prompt_gemini(
    task_cfg: config.LLMTaskConfig,
    prompt: str,
    *,
    response_json_schema: Mapping[str, object] | None = None,
) -> LLMResponse:
    """
    Execute a prompt using Google Gemini and return the response.
    """
    timer_start = time.perf_counter()
    client = config.settings_llm_vendor.get_llm_client("GEMINI", task_cfg.tier)
    if client is None:
        raise OSError(f"Gemini client for tier '{task_cfg.tier}' is not configured.")
    logging.info(
        "_exec_prompt_gemini('%s') - Using {%s - %s - %s} | Web search: %s | Reasoning: %s | Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
        task_cfg.use_web_search,
        task_cfg.reasoning_effort,
    )
    print(prompt if _is_debug_mode() else "<prompt omitted>")

    """Execute prompt using Google Gemini client with grounding (web search)."""
    from google.genai.types import GenerateContentConfig, GoogleSearch, ThinkingConfig, ThinkingLevel, Tool

    model = task_cfg.model
    config_kwargs: dict[str, object] = {}
    if task_cfg.use_web_search:
        config_kwargs["tools"] = [Tool(google_search=GoogleSearch())]
    if task_cfg.reasoning_effort is not None:
        model_name = model.rsplit("/", maxsplit=1)[-1].lower()
        if model_name.startswith("gemini-2.5-"):
            max_budget = 32768 if model_name.startswith("gemini-2.5-pro") else 24576
            config_kwargs["thinking_config"] = ThinkingConfig(
                thinking_budget={
                    "low": 1024,
                    "medium": 8192,
                    "high": max_budget,
                }[task_cfg.reasoning_effort.lower()]
            )
        else:
            config_kwargs["thinking_config"] = ThinkingConfig(
                thinking_level={
                    "low": ThinkingLevel.LOW,
                    "medium": ThinkingLevel.MEDIUM,
                    "high": ThinkingLevel.HIGH,
                }[task_cfg.reasoning_effort.lower()]
            )
    if response_json_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_json_schema"] = dict(response_json_schema)
    gemini_cfg = GenerateContentConfig(**config_kwargs)

    ai_resp = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=gemini_cfg,
    )

    timer_end = time.perf_counter()
    token_usage_input = 0
    token_usage_output = 0
    token_usage_thought = 0
    token_usage_tool = 0
    token_usage_cache = 0
    token_usage_total = 0
    if ai_resp.usage_metadata:
        token_usage_input = ai_resp.usage_metadata.prompt_token_count or 0
        token_usage_output = ai_resp.usage_metadata.candidates_token_count or 0
        token_usage_thought = ai_resp.usage_metadata.thoughts_token_count or 0
        token_usage_tool = ai_resp.usage_metadata.tool_use_prompt_token_count or 0
        token_usage_cache = ai_resp.usage_metadata.cached_content_token_count or 0
        token_usage_total = ai_resp.usage_metadata.total_token_count or 0

    result = LLMResponse(
        completion=ai_resp.text or "",
        time_taken_ms=int((timer_end - timer_start) * 1000),
        tokens_prompt=token_usage_input,
        tokens_completion=token_usage_output,
        tokens_thought=token_usage_thought,
        tokens_tool=token_usage_tool,
        tokens_cache=token_usage_cache,
        tokens_total=token_usage_total,
        is_error=(
            (ai_resp.prompt_feedback is not None and ai_resp.prompt_feedback.block_reason is not None)
            or len(ai_resp.candidates or []) == 0
        ),
    )

    logging.info(
        "_exec_prompt_gemini('%s') - Time taken: %d ms | Tokens used: {prompt: %d, completion: %d, thought: %d, tool: %d, cache: %d, total: %d} | Is error: %s | Response:",
        task_cfg.task_name,
        result.time_taken_ms,
        result.tokens_prompt,
        result.tokens_completion,
        result.tokens_thought,
        result.tokens_tool,
        result.tokens_cache,
        result.tokens_total,
        result.is_error,
    )
    if result.is_error:
        result.error_msg = result.completion
    print(result.completion if _is_debug_mode() else "<response omitted>")

    return result
