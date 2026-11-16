import time
import typing
from typing import Literal

import openai
import pydantic_settings
from azure.identity import EnvironmentCredential, get_bearer_token_provider
from google import genai
from google.genai.types import HttpOptions
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_QUOTE_TYPES = {"EQUITY", "ETF", "MUTUALFUND"}
ReasoningEffort = Literal["High", "Medium", "Low"]
TokenomicsMode = Literal["Standard", "Economy"]

# ----------------------------------------------------------------------#


class LLMClientFactory:
    """Provider-neutral fallback factory used by configured AI tasks.

    The base factory is intentionally instantiable. Each provider method
    returns ``None`` so callers can represent an unsupported provider without
    a special sentinel or an abstract subclass.
    """

    def create_gemini_client(self) -> genai.Client | None:
        """Return a configured Gemini client, or ``None`` when unsupported."""
        return None

    def create_openai_client(self) -> openai.AsyncOpenAI | None:
        """Return a configured OpenAI client, or ``None`` when unsupported."""
        return None

    def create_azure_openai_client(self) -> openai.AsyncOpenAI | None:
        """Return a configured Azure OpenAI client, or ``None`` when unsupported."""
        return None

    def create_openrouter_client(self) -> openai.AsyncOpenAI | None:
        """Return a configured OpenRouter client, or ``None`` when unsupported."""
        return None


class GeminiClientFactory(LLMClientFactory):
    def __init__(self, *, api_key: str, timeout_sec: float = 180):
        """Create a reusable Gemini client immediately.

        Args:
            api_key: Gemini API key passed to the provider SDK.
            timeout_sec: Request timeout in seconds. Non-positive values use
                the 30-second fallback; positive values are converted to
                integer milliseconds for the Gemini HTTP options.
        """
        timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.client = genai.Client(api_key=api_key, http_options=HttpOptions(timeout=int(timeout_sec * 1000)))

    def create_gemini_client(self) -> genai.Client:
        """Return the configured reusable Gemini client."""
        return self.client


class OpenRouterClientFactory(LLMClientFactory):
    def __init__(self, *, endpoint: str, api_key: str, timeout_sec: float = 180):
        """Create a reusable OpenRouter client immediately.

        Args:
            endpoint: OpenAI-compatible OpenRouter base URL.
            api_key: OpenRouter API key.
            timeout_sec: Request timeout in seconds. Non-positive values use
                the 30-second fallback.
        """
        timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=endpoint, project="FinHub", timeout=timeout_sec)

    def create_openrouter_client(self) -> openai.AsyncOpenAI:
        """Return the configured reusable OpenRouter client."""
        return self.client


class OpenAIClientFactory(LLMClientFactory):
    def __init__(self, *, api_key: str, timeout_sec: float = 180):
        """Create a reusable direct OpenAI client immediately.

        Args:
            api_key: OpenAI API key.
            timeout_sec: Request timeout in seconds. Non-positive values use
                the 30-second fallback.
        """
        timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.client = openai.AsyncOpenAI(api_key=api_key, project="FinHub", timeout=timeout_sec)

    def create_openai_client(self) -> openai.AsyncOpenAI:
        """Return the configured reusable OpenAI client."""
        return self.client


class AzureOpenAIClientFactory(LLMClientFactory):
    def __init__(self, *, endpoint: str, timeout_sec: float = 180):
        """Create a lazy Azure OpenAI client factory.

        Args:
            endpoint: Azure OpenAI-compatible base URL retained for each client.
            timeout_sec: Request timeout in seconds. Non-positive values use
                the 30-second fallback.

        Notes:
            Construction does not acquire Azure credentials or create a
            provider client. :meth:`create_azure_openai_client` performs that
            work on first use and after the refresh interval.
        """
        self.client = None
        self.timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.endpoint = endpoint
        self.last_client_timestamp = 0

    def create_azure_openai_client(self) -> openai.AsyncOpenAI:
        """Return an Azure OpenAI client with a refreshed bearer token.

        Returns:
            The current client. The first call always creates it, and calls
            after 30 minutes replace it with a newly authenticated client.

        Raises:
            Exception: Azure credential, token, or client-construction failures
                propagate to the caller.
        """
        now = time.time()
        if self.client is None or now - self.last_client_timestamp > 1800:
            token_provider = get_bearer_token_provider(EnvironmentCredential(), "https://ai.azure.com/.default")
            self.client = openai.AsyncOpenAI(
                api_key=token_provider(), base_url=self.endpoint, project="FinHub", timeout=self.timeout_sec
            )
            self.last_client_timestamp = now
        return self.client


# ----------------------------------------------------------------------#


class LLMConfig(BaseSettings):
    """One vendor-tier catalog entry.

    ``models`` accepts either a set or a comma-separated environment value.
    String entries are trimmed, empty entries are discarded, and duplicates
    collapse into the returned set.
    """

    vendor_name: str = ""
    api_tier: str = ""
    api_key: str = Field(default="")
    endpoint: str = Field(default="")
    models: typing.Annotated[set[str], pydantic_settings.NoDecode] = Field(default=[])

    @field_validator("models", mode="before")
    @classmethod
    def _decode_models(cls, v: object) -> object:
        if isinstance(v, str):
            return set(model.strip() for model in v.split(",") if model.strip())
        return v


class LLMTaskConfig(BaseSettings):
    """LLM configuration for a task.

    ``reasoning_effort`` is case-insensitive, trims whitespace, and normalizes
    non-empty values to ``High``, ``Medium``, or ``Low``. An empty value is
    treated as omitted.
    """

    task_name: str = ""
    vendor: str = ""
    tier: str = ""
    model: str = ""
    reasoning_effort: ReasoningEffort | None = None
    use_web_search: bool = False
    max_tool_calls: int = 0

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _normalize_reasoning_effort(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            return v.strip().title() or None
        return v


class OpenAIExecutionSettings(BaseSettings):
    """Runtime controls shared by OpenAI-compatible providers."""

    max_concurrent_requests: int = Field(default=2, ge=1)
    rate_limit_max_wait_seconds: float = Field(default=10 * 60, ge=0)
    rate_limit_initial_backoff_seconds: float = Field(default=5, gt=0)
    rate_limit_max_backoff_seconds: float = Field(default=60, gt=0)
    model_config = SettingsConfigDict(
        env_file="ai_vendors.env",
        env_file_encoding="utf-8",
        env_prefix="FINHUB_OPENAI_EXECUTION_",
        extra="ignore",
    )


class LLMVendorSettings(BaseSettings):
    vendors: dict[str, dict[str, LLMConfig]] = Field(alias="FINHUB_LLM", default={})
    client_factories: dict[str, dict[str, LLMClientFactory]] = {}
    model_config = SettingsConfigDict(
        env_file="ai_vendors.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="ignore",
    )

    def get_llm_client(
        self, vendor: str, tier: str, timeout_sec: float = 180
    ) -> genai.Client | openai.AsyncOpenAI | None:
        """Return the configured client for an AI vendor and service tier.

        Args:
            vendor: Case-insensitive provider name. Azure OpenAI and OpenRouter
                also accept space- and underscore-separated aliases.
            tier: Case-insensitive configured service-tier name.
            timeout_sec: Retained for caller compatibility; client timeouts are
                set when factories are constructed.

        Returns:
            The provider client, or ``None`` when the vendor, tier, or factory
            is unavailable.

        Notes:
            Surrounding whitespace is ignored. Credential and factory failures
            propagate.
        """
        del timeout_sec
        v_name = vendor.strip().upper()
        a_tier = tier.strip().upper()
        match v_name:
            case "AZUREOPENAI" | "AZURE OPENAI" | "AZURE_OPENAI":
                return (
                    self.client_factories["AZURE_OPENAI"][a_tier].create_azure_openai_client()
                    if "AZURE_OPENAI" in self.client_factories and a_tier in self.client_factories["AZURE_OPENAI"]
                    else None
                )
            case "OPENAI":
                return (
                    self.client_factories["OPENAI"][a_tier].create_openai_client()
                    if "OPENAI" in self.client_factories and a_tier in self.client_factories["OPENAI"]
                    else None
                )
            case "OPENROUTER" | "OPEN ROUTER" | "OPEN_ROUTER":
                return (
                    self.client_factories["OPEN_ROUTER"][a_tier].create_openrouter_client()
                    if "OPEN_ROUTER" in self.client_factories and a_tier in self.client_factories["OPEN_ROUTER"]
                    else None
                )
            case "GEMINI":
                return (
                    self.client_factories["GEMINI"][a_tier].create_gemini_client()
                    if "GEMINI" in self.client_factories and a_tier in self.client_factories["GEMINI"]
                    else None
                )
            case _:
                return None


class LLMTaskSettings(BaseSettings):
    """Task routing and tokenomics settings.

    ``Economy`` is accepted case-insensitively. Missing, empty, non-string, or
    unsupported tokenomics values normalize to ``Standard``. Explicit
    constructor values follow normal Pydantic settings precedence over the
    process environment.
    """

    tasks: dict[str, LLMTaskConfig] = Field(alias="FINHUB_LLM_TASK", default={})
    tokenomics_mode: TokenomicsMode = Field(alias="FINHUB_LLM_TOKENOMICS_MODE", default="Standard")
    model_config = SettingsConfigDict(
        env_file="ai_tasks.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="ignore",
    )

    @field_validator("tokenomics_mode", mode="before")
    @classmethod
    def _normalize_tokenomics_mode(cls, v: object) -> str:
        supported_modes = {mode.casefold(): mode for mode in typing.get_args(TokenomicsMode)}
        return supported_modes.get(v.strip().casefold(), "Standard") if isinstance(v, str) else "Standard"


settings_openai_execution = OpenAIExecutionSettings()
settings_llm_vendor = LLMVendorSettings()
settings_llm_task = LLMTaskSettings()

# ----------------------------------------------------------------------#


class FinHubProxySettings(BaseSettings):
    """Node-chaining mode and optional web-crawl and AI-task node URLs."""

    proxy_mode: Literal["None", "Redirect", "Forward"] = Field(default="None", alias="FINHUB_PROXY_MODE")
    url_web_crawl_node: str = Field(default="", alias="FINHUB_URL_WEB_CRAWL_NODE")
    url_ai_task_node: str = Field(default="", alias="FINHUB_URL_AI_TASK_NODE")
    model_config = SettingsConfigDict(
        env_file="finhub_proxy_config.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings_finhub_proxy = FinHubProxySettings()

# ----------------------------------------------------------------------#


class AppSettings(BaseSettings):
    """Application authentication settings."""

    api_key: str = Field(default="", alias="FINHUB_API_KEY")
    model_config = SettingsConfigDict(
        env_file="app_config.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings_app = AppSettings()
