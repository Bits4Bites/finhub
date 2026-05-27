import logging
import os
import time
from typing import Literal

from google.genai import types
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionUserMessageParam
from openai.types.responses import WebSearchPreviewToolParam
from openai.types.responses.web_search_preview_tool_param import UserLocation
from pydantic import BaseModel

from ..config import LLMTaskConfig, LLMTaskConfigOverride, settings_llm_task, settings_llm_vendor
from ..models.ai import LLMResponse

ThinkingLevel = Literal["LOW", "MEDIUM", "HIGH"]

# ----------------------------------------------------------------------#


class PromptConfig(BaseModel):
    use_web_search: bool = False
    country: str | None = None  # for web search location context
    thinking_level: ThinkingLevel | None = None


async def _exec_prompt_openai_client(
    client: AsyncOpenAI,
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
) -> LLMResponse:
    """
    Execute a prompt using OpenAI client and return the response.
    """
    start = time.perf_counter()
    logging.info(
        "_exec_prompt_openai_client('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(prompt)
    else:
        print("<prompt omitted>")

    if prompt_cfg and prompt_cfg.use_web_search:
        # use response API with web search tool
        ai_response = await client.responses.create(
            model=task_cfg.model,
            temperature=0.10,
            tools=[
                WebSearchPreviewToolParam(
                    type="web_search_preview",
                    user_location=UserLocation(type="approximate", country=prompt_cfg.country)
                    if prompt_cfg.country
                    else None,
                ),
            ],
            input=prompt,
        )
        end = time.perf_counter()
        result = LLMResponse(
            completion=ai_response.output_text,
            time_taken_ms=int((end - start) * 1000),
            tokens_prompt=ai_response.usage.input_tokens if ai_response.usage else 0,
            tokens_completion=ai_response.usage.output_tokens if ai_response.usage else 0,
            tokens_thought=0,
            is_error=not ai_response or ai_response.status != "completed",
        )
    else:
        # use standard chat completion API for non web search tasks
        completion = await client.chat.completions.create(
            # extra_headers={"X-OpenRouter-Title": "FinHub"},
            model=task_cfg.model,
            temperature=0.10,
            messages=[ChatCompletionUserMessageParam(content=prompt, role="user")],
        )
        end = time.perf_counter()
        result = LLMResponse(
            completion=completion.choices[0].message.content or "" if len(completion.choices) > 0 else "",
            time_taken_ms=int((end - start) * 1000),
            tokens_prompt=completion.usage.prompt_tokens if completion.usage else 0,
            tokens_completion=completion.usage.completion_tokens if completion.usage else 0,
            tokens_thought=0,
            is_error=len(completion.choices) == 0,
        )

    logging.info(
        "_exec_prompt_openai_client('%s') - Time taken: %d ms / Tokens used: %d/%d/%d / Is error: %s - Response:",
        task_cfg.task_name,
        result.time_taken_ms,
        result.tokens_prompt,
        result.tokens_thought,
        result.tokens_completion,
        result.is_error,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(result.completion)
    else:
        print("<response omitted>")

    return result


async def _exec_prompt_azure_openai(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
) -> LLMResponse:
    """
    Execute a prompt using Azure OpenAI and return the response.
    """
    client = settings_llm_vendor.get_llm_client("AZURE_OPENAI", task_cfg.tier)
    if client is None:
        raise OSError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await _exec_prompt_openai_client(
        client,
        task_cfg,
        prompt,
        prompt_cfg,
    )


async def _exec_prompt_openrouter(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
) -> LLMResponse:
    """
    Execute a prompt using OpenRouter and return the response.
    """
    client = settings_llm_vendor.get_llm_client("OPEN_ROUTER", task_cfg.tier)
    if client is None:
        raise OSError(f"OpenRouter client for tier '{task_cfg.tier}' is not configured.")
    return await _exec_prompt_openai_client(
        client,
        task_cfg,
        prompt,
        prompt_cfg,
    )


async def _exec_prompt_openai(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
) -> LLMResponse:
    """
    Execute a prompt using OpenAI and return the response.
    """
    client = settings_llm_vendor.get_llm_client("OPENAI", task_cfg.tier)
    if client is None:
        raise OSError(f"OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await _exec_prompt_openai_client(
        client,
        task_cfg,
        prompt,
        prompt_cfg,
    )


async def _exec_prompt_gemini(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
) -> LLMResponse:
    """
    Execute a prompt using Google Gemini and return the response.
    """
    start = time.perf_counter()
    client = settings_llm_vendor.get_llm_client("GEMINI", task_cfg.tier)
    if client is None:
        raise OSError(f"Gemini client for tier '{task_cfg.tier}' is not configured.")
    logging.info(
        "_exec_prompt_gemini('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(prompt)
    else:
        print("<prompt omitted>")

    thinking_config = None
    if prompt_cfg and prompt_cfg.thinking_level and task_cfg.model.startswith("gemini-3"):
        thinking_config = types.ThinkingConfig(thinking_level=types.ThinkingLevel(prompt_cfg.thinking_level))
    ai_response = client.models.generate_content(
        model=task_cfg.model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.10, thinking_config=thinking_config),
    )
    end = time.perf_counter()
    result = LLMResponse(
        completion=ai_response.text or "",
        time_taken_ms=int((end - start) * 1000),
        tokens_prompt=ai_response.usage_metadata.prompt_token_count or 0 if ai_response.usage_metadata else 0,
        tokens_completion=ai_response.usage_metadata.candidates_token_count or 0 if ai_response.usage_metadata else 0,
        tokens_thought=ai_response.usage_metadata.thoughts_token_count or 0 if ai_response.usage_metadata else 0,
        tokens_total=ai_response.usage_metadata.total_token_count or 0 if ai_response.usage_metadata else 0,
        is_error=(
            (ai_response.prompt_feedback is not None and ai_response.prompt_feedback.block_reason is not None)
            or len(ai_response.candidates or []) == 0
        ),
    )

    logging.info(
        "_exec_prompt_gemini('%s') - Time taken: %d ms / Tokens used: %d/%d/%d / Is error: %s - Response:",
        task_cfg.task_name,
        result.time_taken_ms,
        result.tokens_prompt,
        result.tokens_thought,
        result.tokens_completion,
        result.is_error,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(result.completion)
    else:
        print("<response omitted>")

    return result


async def ai_exec_prompt(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
    *,
    llm_config_override: LLMTaskConfigOverride = None,
) -> LLMResponse:
    """
    Executes a prompt using the specified LLM task configuration.
    """
    used_vendor = (llm_config_override.vendor if llm_config_override else task_cfg.vendor).upper()
    match used_vendor:
        case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI":
            return await _exec_prompt_azure_openai(
                llm_config_override if llm_config_override else task_cfg,
                prompt,
                prompt_cfg,
            )
        case "OPENAI":
            return await _exec_prompt_openai(
                llm_config_override if llm_config_override else task_cfg,
                prompt,
                prompt_cfg,
            )
        case "OPENROUTER" | "OPEN ROUTER" | "OPEN_ROUTER":
            return await _exec_prompt_openrouter(
                llm_config_override if llm_config_override else task_cfg,
                prompt,
                prompt_cfg,
            )
        case "GEMINI":
            return await _exec_prompt_gemini(
                llm_config_override if llm_config_override else task_cfg,
                prompt,
                prompt_cfg,
            )
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")


async def ai_exec_task(
    task_id: str,
    prompt: str,
    country: str = "",
    *,
    thinking_level: ThinkingLevel = None,
    llm_config_override: LLMTaskConfigOverride = None,
) -> LLMResponse:
    """
    Executes a task using the appropriate LLM based on the task configuration.
    """
    task_cfg = settings_llm_task.tasks.get(task_id)
    if not task_cfg:
        raise ValueError(f"LLM task configuration for task_id '{task_id}' not found.")
    prompt_cfg = PromptConfig(
        use_web_search=task_cfg.model.startswith("gpt-5"),
        country=country,
        thinking_level=thinking_level,
    )
    return await ai_exec_prompt(task_cfg, prompt, prompt_cfg, llm_config_override=llm_config_override)
