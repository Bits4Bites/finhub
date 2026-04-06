import logging
import os
import time
from typing import Optional, Literal

from openai.types.chat import ChatCompletionUserMessageParam
from openai.types.responses import WebSearchPreviewToolParam
from openai.types.responses.web_search_preview_tool_param import UserLocation
from openai import AsyncOpenAI

from google import genai
from google.genai import types
from pydantic import BaseModel

from ..config import LLMTaskConfig
from ..models.finhub import LLMResponse

geminiClients: dict[str, genai.Client] = {}
openAIClients: dict[str, AsyncOpenAI] = {}
openRouterClients: dict[str, AsyncOpenAI] = {}
azureOpenAIClients: dict[str, AsyncOpenAI] = {}


class PromptConfig(BaseModel):
    use_web_search: bool = False
    country: Optional[str] = None  # for web search location context
    thinking_level: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None


async def ai_exec_prompt_openai_client(
    client: AsyncOpenAI, task_cfg: LLMTaskConfig, prompt: str, prompt_cfg: PromptConfig = None
) -> LLMResponse:
    """
    Execute a prompt using OpenAI client and return the response.
    """
    start = time.perf_counter()
    logging.info(
        "ai_exec_prompt_openai_client('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(prompt)

    if prompt_cfg and prompt_cfg.use_web_search:
        # use response API with web search tool
        ai_response = await client.responses.create(
            model=task_cfg.model,
            tools=[
                WebSearchPreviewToolParam(
                    type="web_search_preview",
                    user_location=UserLocation(type="approximate", country=prompt_cfg.country),
                ),
            ],
            input=prompt,
        )
        end = time.perf_counter()
        result = LLMResponse(
            completion=ai_response.output_text,
            time_taken_ms=int((end - start) * 1000),
            tokens_prompt=ai_response.usage.input_tokens,
            tokens_completion=ai_response.usage.output_tokens,
            tokens_thought=0,
            is_error=not ai_response or ai_response.status != "completed",
        )
    else:
        # use standard chat completion API for non web search tasks
        completion = await client.chat.completions.create(
            extra_headers={"X-OpenRouter-Title": "FinHub"},
            model=task_cfg.model,
            temperature=0.0,
            messages=[ChatCompletionUserMessageParam(content=prompt, role="user")],
        )
        end = time.perf_counter()
        result = LLMResponse(
            completion=completion.choices[0].message.content if len(completion.choices) > 0 else "",
            time_taken_ms=int((end - start) * 1000),
            tokens_prompt=completion.usage.prompt_tokens,
            tokens_completion=completion.usage.completion_tokens,
            tokens_thought=0,
            is_error=len(completion.choices) == 0,
        )

    logging.info(
        "ai_exec_prompt_openai_client('%s') - Time taken: %d ms / Tokens used: %d/%d/%d / Is error: %s - Response:",
        task_cfg.task_name,
        result.time_taken_ms,
        result.tokens_prompt,
        result.tokens_thought,
        result.tokens_completion,
        result.is_error,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(result.completion)

    return result


async def ai_exec_prompt_azure_openai(
    task_cfg: LLMTaskConfig, prompt: str, prompt_cfg: PromptConfig = None
) -> LLMResponse:
    """
    Execute a prompt using Azure OpenAI and return the response.
    """
    client = azureOpenAIClients.get(task_cfg.tier.upper())
    if client is None:
        raise EnvironmentError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await ai_exec_prompt_openai_client(client, task_cfg, prompt, prompt_cfg)


async def ai_exec_prompt_openrouter(
    task_cfg: LLMTaskConfig, prompt: str, prompt_cfg: PromptConfig = None
) -> LLMResponse:
    """
    Execute a prompt using OpenRouter and return the response.
    """
    client = openRouterClients.get(task_cfg.tier.upper())
    if client is None:
        raise EnvironmentError(f"OpenRouter client for tier '{task_cfg.tier}' is not configured.")
    return await ai_exec_prompt_openai_client(client, task_cfg, prompt, prompt_cfg)


async def ai_exec_prompt_openai(task_cfg: LLMTaskConfig, prompt: str, prompt_cfg: PromptConfig = None) -> LLMResponse:
    """
    Execute a prompt using OpenAI and return the response.
    """
    client = openAIClients.get(task_cfg.tier.upper())
    if client is None:
        raise EnvironmentError(f"OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await ai_exec_prompt_openai_client(client, task_cfg, prompt, prompt_cfg)


async def ai_exec_prompt_gemini(task_cfg: LLMTaskConfig, prompt: str, prompt_cfg: PromptConfig = None) -> LLMResponse:
    """
    Execute a prompt using Google Gemini and return the response.
    """
    start = time.perf_counter()
    client = geminiClients.get(task_cfg.tier.upper())
    if client is None:
        raise EnvironmentError(f"Gemini client for tier '{task_cfg.tier}' is not configured.")
    logging.info(
        "ai_exec_prompt_gemini('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        task_cfg.vendor,
        task_cfg.tier,
        task_cfg.model,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(prompt)

    thinking_config = None
    if prompt_cfg and prompt_cfg.thinking_level and task_cfg.model.startswith("gemini-3"):
        thinking_config = types.ThinkingConfig(thinking_level=types.ThinkingLevel(prompt_cfg.thinking_level))
    ai_response = client.models.generate_content(
        model=task_cfg.model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, thinking_config=thinking_config),
    )
    end = time.perf_counter()
    result = LLMResponse(
        completion=ai_response.text,
        time_taken_ms=int((end - start) * 1000),
        tokens_prompt=ai_response.usage_metadata.prompt_token_count,
        tokens_completion=ai_response.usage_metadata.candidates_token_count,
        tokens_thought=(
            ai_response.usage_metadata.thoughts_token_count if ai_response.usage_metadata.thoughts_token_count else 0
        ),
        is_error=(
            (ai_response.prompt_feedback and ai_response.prompt_feedback.block_reason)
            or len(ai_response.candidates) == 0
        ),
    )

    logging.info(
        "ai_exec_prompt_gemini('%s') - Time taken: %d ms / Tokens used: %d/%d/%d / Is error: %s - Response:",
        task_cfg.task_name,
        result.time_taken_ms,
        result.tokens_prompt,
        result.tokens_thought,
        result.tokens_completion,
        result.is_error,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(result.completion)

    return result


async def ai_exec_prompt(task_cfg: LLMTaskConfig, prompt: str, prompt_cfg: PromptConfig = None) -> LLMResponse:
    """
    Executes a prompt using the specified LLM task configuration.
    """
    match task_cfg.vendor.upper():
        case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI":
            return await ai_exec_prompt_azure_openai(task_cfg, prompt, prompt_cfg)
        case "OPENAI":
            return await ai_exec_prompt_openai(task_cfg, prompt, prompt_cfg)
        case "OPENROUTER" | "OPEN ROUTER" | "OPEN_ROUTER":
            return await ai_exec_prompt_openrouter(task_cfg, prompt, prompt_cfg)
        case "GEMINI":
            return await ai_exec_prompt_gemini(task_cfg, prompt, prompt_cfg)
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")
