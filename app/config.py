import time
from abc import ABC
from typing import Literal

import openai
from azure.identity import EnvironmentCredential, get_bearer_token_provider
from google import genai
from google.genai.types import HttpOptions
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_QUOTE_TYPES = {"EQUITY", "ETF", "MUTUALFUND"}

# ----------------------------------------------------------------------#


class LLMClientFactory(ABC):
    # @abstractmethod
    def create_gemini_client(self) -> genai.Client:
        pass

    # @abstractmethod
    def create_openai_client(self) -> openai.AsyncOpenAI:
        pass

    # @abstractmethod
    def create_azure_openai_client(self) -> openai.AsyncOpenAI:
        pass

    # @abstractmethod
    def create_openrouter_client(self) -> openai.AsyncOpenAI:
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
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=endpoint, project="FinHub", timeout=timeout_sec)

    def create_openrouter_client(self) -> openai.AsyncOpenAI:
        return self.client


class OpenAIClientFactory(LLMClientFactory):
    def __init__(self, *, api_key: str, timeout_sec: float = 180):
        timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.client = openai.AsyncOpenAI(api_key=api_key, project="FinHub", timeout=timeout_sec)

    def create_openai_client(self) -> openai.AsyncOpenAI:
        return self.client


class AzureOpenAIClientFactory(LLMClientFactory):
    def __init__(self, *, endpoint: str, timeout_sec: float = 180):
        self.client = None
        self.timeout_sec = timeout_sec if timeout_sec > 0 else 30
        self.endpoint = endpoint
        self.last_client_timestamp = 0

    def create_azure_openai_client(self) -> openai.AsyncOpenAI:
        now = time.time()
        if now - self.last_client_timestamp > 1800:  # 30 mins
            token_provider = get_bearer_token_provider(EnvironmentCredential(), "https://ai.azure.com/.default")
            self.client = openai.AsyncOpenAI(
                api_key=token_provider(), base_url=self.endpoint, project="FinHub", timeout=self.timeout_sec
            )
            self.last_client_timestamp = time.time()
        return self.client


# ----------------------------------------------------------------------#


class LLMConfig(BaseSettings):
    vendor_name: str = ""
    api_tier: str = ""
    api_key: str = Field(default="")
    endpoint: str = Field(default="")
    models: set[str] = Field(default=[])

    @field_validator("models", mode="before")
    @classmethod
    def decode_models(cls, v: str) -> set[str]:
        if isinstance(v, str):
            return set(model.strip() for model in v.split(",") if model.strip())
        return set()


class LLMTaskConfig(BaseSettings):
    """
    LLM configurations for a task. Supply an instance of LLMTaskConfigOverride to override the default LLM configurations for a task.
    """

    task_name: str = ""
    vendor: str = ""
    tier: str = ""
    model: str = ""
    temperature: float = 0.2


class LLMTaskConfigOverride(LLMTaskConfig):
    """
    Supply an instance of LLMTaskConfigOverride to override the default LLM configurations for a task.
    """

    pass


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
        v_name = vendor.upper()
        a_tier = tier.upper()
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
    tasks: dict[str, LLMTaskConfig] = Field(alias="FINHUB_LLM_TASK", default={})
    model_config = SettingsConfigDict(
        env_file="ai_tasks.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="ignore",
    )

    # def get_llm_client(self, task_id, timeout_sec: float = 180) -> genai.Client | openai.AsyncOpenAI | None:
    #     t_id = task_id.upper()
    #     task_config = self.tasks.get(t_id)
    #     return settings_llm_vendor.get_llm_client(task_config.vendor, task_config.tier, timeout_sec) \
    #     if task_config
    #     else None


settings_llm_vendor = LLMVendorSettings()
settings_llm_task = LLMTaskSettings()

# ----------------------------------------------------------------------#


class HttpProxy(BaseModel):
    id: int = 0
    ip: str = ""
    port: int = 0
    protocol: str = ""
    anonymity: str = ""
    speed: float = 0.0
    https: int = 0
    country: str = ""
    city: str = ""
    connect_string: str = ""


class FinHubProxySettings(BaseSettings):
    proxy_mode: Literal["None", "Redirect", "Forward"] = Field(default="None", alias="FINHUB_PROXY_MODE")
    url_web_crawl_node: str = Field(default="", alias="FINHUB_URL_WEB_CRAWL_NODE")
    fetch_website_via_proxy: bool = Field(default=False, alias="FINHUB_FETCH_WEBSITE_VIA_PROXY")
    http_proxies: list[HttpProxy] | None = None
    model_config = SettingsConfigDict(
        env_file="finhub_proxy_config.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings_finhub_proxy = FinHubProxySettings()

# ----------------------------------------------------------------------#


class AppSettings(BaseSettings):
    api_key: str = Field(default="", alias="FINHUB_API_KEY")
    model_config = SettingsConfigDict(
        env_file="app_config.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings_app = AppSettings()

# ----------------------------------------------------------------------#


class CompanyBriefInfo(BaseSettings):
    symbol: str = Field(default="")
    name: str = Field(default="")
    sector: str = Field(default="")
    market_cap: int = Field(default=0)

    model_config = SettingsConfigDict(
        nested_model_default_partial_update=True,
    )


class MarketIndices(BaseSettings):
    # {index -> {symbol -> CompanyBriefInfo}}
    indices: dict[str, dict[str, CompanyBriefInfo]] = Field(default={})
    model_config = SettingsConfigDict(
        nested_model_default_partial_update=True,
    )


market_indices = MarketIndices()
