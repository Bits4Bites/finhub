import logging
import os
import time
from collections.abc import Mapping

import openai
from pydantic import BaseModel

from .. import config

# ----------------------------------------------------------------------#


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


def _is_debug_mode() -> bool:
    return os.getenv("LLM_DEBUG_MODE", "").lower() in ("1", "true", "yes")


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
    timer_start = time.perf_counter()
    logging.info(
        "_exec_prompt_openai_client('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
    )
    print(prompt if _is_debug_mode() else "<prompt omitted>")

    model = task_cfg.model
    reasoning_effort = task_cfg.reasoning_effort
    use_web_search = task_cfg.use_web_search

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
        if response_json_schema is not None:
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": dict(response_json_schema),
                },
            }
        ai_resp = await client.chat.completions.create(**request_kwargs)
    else:
        request_kwargs: dict[str, object] = {
            "model": model,
            "input": prompt,
        }
        if use_web_search:
            request_kwargs["max_tool_calls"] = _MAX_TOOL_CALLS_BY_REASONING[reasoning_effort]
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
        if response_json_schema is not None:
            request_kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": dict(response_json_schema),
                }
            }
        ai_resp = await client.responses.create(**request_kwargs)

    timer_end = time.perf_counter()
    token_usage_input = 0
    token_usage_output = 0
    token_usage_thought = 0
    token_usage_tool = 0
    token_usage_cache = 0
    token_usage_total = 0
    completion = ""

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
    )

    logging.info(
        "_exec_prompt_openai_client('%s') - Time taken: %d ms | Tokens used: {prompt: %d, completion: %d, thought: %d, tool: %d, cache: %d, total: %d} / Is error: %s - Response:",
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
        "_exec_prompt_gemini('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
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
        "_exec_prompt_gemini('%s') - Time taken: %d ms | Tokens used: {prompt: %d, completion: %d, thought: %d, tool: %d, cache: %d, total: %d} / Is error: %s - Response:",
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
