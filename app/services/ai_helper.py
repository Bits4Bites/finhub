import logging
import os
import time
from abc import ABC
from typing import Optional, Literal

from azure.identity import get_bearer_token_provider, EnvironmentCredential
from google.genai.types import HttpOptions
from openai.types.chat import ChatCompletionUserMessageParam
from openai.types.responses import WebSearchPreviewToolParam
from openai.types.responses.web_search_preview_tool_param import UserLocation
from openai import AsyncOpenAI

from google import genai
from google.genai import types
from pydantic import BaseModel

from ..config import LLMTaskConfig, LLMTaskConfigOverride
from ..models.finhub import LLMResponse

geminiClients: dict[str, "LLMClientFactory"] = {}
openAIClients: dict[str, "LLMClientFactory"] = {}
openRouterClients: dict[str, "LLMClientFactory"] = {}
azureOpenAIClients: dict[str, "LLMClientFactory"] = {}

ThinkingLevel = Literal["LOW", "MEDIUM", "HIGH"]

# ----------------------------------------------------------------------#


class LLMClientFactory(ABC):
    # @abstractmethod
    def create_gemini_client(self) -> genai.Client:
        pass

    # @abstractmethod
    def create_openai_client(self) -> AsyncOpenAI:
        pass

    # @abstractmethod
    def create_azure_openai_client(self) -> AsyncOpenAI:
        pass

    # @abstractmethod
    def create_openrouter_client(self) -> AsyncOpenAI:
        pass


class GeminiClientFactory(LLMClientFactory):
    def __init__(self, *, api_key: str, timeout_sec: float = 180):
        timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.client = genai.Client(api_key=api_key, http_options=HttpOptions(timeout=int(timeout_sec * 1000)))

    def create_gemini_client(self) -> genai.Client:
        return self.client


class OpenRouterClientFactory(LLMClientFactory):
    def __init__(self, *, endpoint: str, api_key: str, timeout_sec: float = 180):
        timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.client = AsyncOpenAI(api_key=api_key, base_url=endpoint, project="FinHub", timeout=timeout_sec)

    def create_openrouter_client(self) -> AsyncOpenAI:
        return self.client


class OpenAIClientFactory(LLMClientFactory):
    def __init__(self, *, api_key: str, timeout_sec: float = 180):
        timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.client = AsyncOpenAI(api_key=api_key, project="FinHub", timeout=timeout_sec)

    def create_openai_client(self) -> AsyncOpenAI:
        return self.client


class AzureOpenAIClientFactory(LLMClientFactory):
    def __init__(self, *, endpoint: str, timeout_sec: float = 180):
        self.client = None
        self.timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.endpoint = endpoint
        self.last_client_timestamp = 0

    def create_azure_openai_client(self) -> AsyncOpenAI:
        now = time.time()
        if now - self.last_client_timestamp > 1800:  # 30 mins
            token_provider = get_bearer_token_provider(EnvironmentCredential(), "https://ai.azure.com/.default")
            self.client = AsyncOpenAI(
                api_key=token_provider(), base_url=self.endpoint, project="FinHub", timeout=self.timeout_sec
            )
            self.last_client_timestamp = time.time()
        return self.client


# ----------------------------------------------------------------------#


class PromptConfig(BaseModel):
    use_web_search: bool = False
    country: Optional[str] = None  # for web search location context
    thinking_level: Optional[ThinkingLevel] = None


async def ai_exec_prompt_openai_client(
    client: AsyncOpenAI,
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
    *,
    llm_config_override: LLMTaskConfigOverride = None,
) -> LLMResponse:
    """
    Execute a prompt using OpenAI client and return the response.
    """
    start = time.perf_counter()
    logging.info(
        "ai_exec_prompt_openai_client('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        llm_config_override.vendor if llm_config_override else task_cfg.vendor,
        llm_config_override.tier if llm_config_override else task_cfg.tier,
        llm_config_override.model if llm_config_override else task_cfg.model,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(prompt)
    else:
        print("<prompt omitted>")

    if prompt_cfg and prompt_cfg.use_web_search:
        # use response API with web search tool
        ai_response = await client.responses.create(
            model=llm_config_override.model if llm_config_override else task_cfg.model,
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
            tokens_prompt=ai_response.usage.input_tokens if ai_response.usage else 0,
            tokens_completion=ai_response.usage.output_tokens if ai_response.usage else 0,
            tokens_thought=0,
            is_error=not ai_response or ai_response.status != "completed",
        )
    else:
        # use standard chat completion API for non web search tasks
        completion = await client.chat.completions.create(
            # extra_headers={"X-OpenRouter-Title": "FinHub"},
            model=llm_config_override.model if llm_config_override else task_cfg.model,
            temperature=0.0,
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
    else:
        print("<response omitted>")

    return result


async def ai_exec_prompt_azure_openai(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
    *,
    llm_config_override: LLMTaskConfigOverride = None,
) -> LLMResponse:
    """
    Execute a prompt using Azure OpenAI and return the response.
    """
    client_fac = azureOpenAIClients.get(task_cfg.tier.upper())
    if client_fac is None:
        raise EnvironmentError(f"Azure OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await ai_exec_prompt_openai_client(
        client_fac.create_azure_openai_client(),
        task_cfg,
        prompt,
        prompt_cfg,
        llm_config_override=llm_config_override,
    )


async def ai_exec_prompt_openrouter(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
    *,
    llm_config_override: LLMTaskConfigOverride = None,
) -> LLMResponse:
    """
    Execute a prompt using OpenRouter and return the response.
    """
    client_fac = openRouterClients.get(task_cfg.tier.upper())
    if client_fac is None:
        raise EnvironmentError(f"OpenRouter client for tier '{task_cfg.tier}' is not configured.")
    return await ai_exec_prompt_openai_client(
        client_fac.create_openrouter_client(),
        task_cfg,
        prompt,
        prompt_cfg,
        llm_config_override=llm_config_override,
    )


async def ai_exec_prompt_openai(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
    *,
    llm_config_override: LLMTaskConfigOverride = None,
) -> LLMResponse:
    """
    Execute a prompt using OpenAI and return the response.
    """
    client_fac = openAIClients.get(task_cfg.tier.upper())
    if client_fac is None:
        raise EnvironmentError(f"OpenAI client for tier '{task_cfg.tier}' is not configured.")
    return await ai_exec_prompt_openai_client(
        client_fac.create_openai_client(),
        task_cfg,
        prompt,
        prompt_cfg,
        llm_config_override=llm_config_override,
    )


async def ai_exec_prompt_gemini(
    task_cfg: LLMTaskConfig,
    prompt: str,
    prompt_cfg: PromptConfig = None,
    *,
    llm_config_override: LLMTaskConfigOverride = None,
) -> LLMResponse:
    """
    Execute a prompt using Google Gemini and return the response.
    """
    start = time.perf_counter()
    client_fac = geminiClients.get(task_cfg.tier.upper())
    if client_fac is None:
        raise EnvironmentError(f"Gemini client for tier '{task_cfg.tier}' is not configured.")
    logging.info(
        "ai_exec_prompt_gemini('%s') - Using vendor/tier/model: %s/%s/%s - Prompt:",
        task_cfg.task_name,
        llm_config_override.vendor if llm_config_override else task_cfg.vendor,
        llm_config_override.tier if llm_config_override else task_cfg.tier,
        llm_config_override.model if llm_config_override else task_cfg.model,
    )
    if os.environ.get("LLM_DEBUG_MODE", "FALSE").upper() == "TRUE":
        print(prompt)
    else:
        print("<prompt omitted>")

    used_model = llm_config_override.model if llm_config_override else task_cfg.model
    client = client_fac.create_gemini_client()
    thinking_config = None
    if prompt_cfg and prompt_cfg.thinking_level and used_model.startswith("gemini-3"):
        thinking_config = types.ThinkingConfig(thinking_level=types.ThinkingLevel(prompt_cfg.thinking_level))
    ai_response = client.models.generate_content(
        model=llm_config_override.model if llm_config_override else task_cfg.model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, thinking_config=thinking_config),
    )
    end = time.perf_counter()
    result = LLMResponse(
        completion=ai_response.text or "",
        time_taken_ms=int((end - start) * 1000),
        tokens_prompt=ai_response.usage_metadata.prompt_token_count or 0 if ai_response.usage_metadata else 0,
        tokens_completion=ai_response.usage_metadata.candidates_token_count or 0 if ai_response.usage_metadata else 0,
        tokens_thought=ai_response.usage_metadata.thoughts_token_count or 0 if ai_response.usage_metadata else 0,
        is_error=(
            (ai_response.prompt_feedback is not None and ai_response.prompt_feedback.block_reason is not None)
            or len(ai_response.candidates or []) == 0
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
            return await ai_exec_prompt_azure_openai(
                task_cfg,
                prompt,
                prompt_cfg,
                llm_config_override=llm_config_override,
            )
        case "OPENAI":
            return await ai_exec_prompt_openai(task_cfg, prompt, prompt_cfg, llm_config_override=llm_config_override)
        case "OPENROUTER" | "OPEN ROUTER" | "OPEN_ROUTER":
            return await ai_exec_prompt_openrouter(
                task_cfg,
                prompt,
                prompt_cfg,
                llm_config_override=llm_config_override,
            )
        case "GEMINI":
            return await ai_exec_prompt_gemini(task_cfg, prompt, prompt_cfg, llm_config_override=llm_config_override)
        case _:
            raise ValueError(f"Unsupported LLM vendor: {task_cfg.vendor}")
