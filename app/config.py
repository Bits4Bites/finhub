from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class LLMTaskConfigOverride(LLMTaskConfig):
    """
    Supply an instance of LLMTaskConfigOverride to override the default LLM configurations for a task.
    """

    pass


class LLMVendorSettings(BaseSettings):
    vendors: dict[str, dict[str, LLMConfig]] = Field(alias="FINHUB_LLM", default={})
    model_config = SettingsConfigDict(
        env_file="ai_vendors.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="ignore",
    )


class LLMTaskSettings(BaseSettings):
    tasks: dict[str, LLMTaskConfig] = Field(alias="FINHUB_LLM_TASK", default={})
    model_config = SettingsConfigDict(
        env_file="ai_tasks.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="ignore",
    )


settings_llm_vendor = LLMVendorSettings()
settings_llm_task = LLMTaskSettings()


class FinHubProxySettings(BaseSettings):
    proxy_mode: Literal["None", "Redirect", "Forward"] = Field(default="None", alias="FINHUB_PROXY_MODE")
    url_web_crawl_node: str = Field(default="", alias="FINHUB_URL_WEB_CRAWL_NODE")
    model_config = SettingsConfigDict(
        env_file="finhub_proxy_config.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings_finhub_proxy = FinHubProxySettings()


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
