from typing import Optional, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    vendor_name: str = ""
    api_tier: str = ""
    api_key: Optional[str] = Field(default=None)
    endpoint: Optional[str] = Field(default=None)
    models: Optional[set[str]] = Field(default=None)

    @field_validator("models", mode="before")
    @classmethod
    def decode_models(cls, v: str) -> set[str]:
        if isinstance(v, str):
            return set(model.strip() for model in v.split(",") if model.strip())
        return set()


class LLMTaskConfig(BaseSettings):
    task_name: str = ""
    vendor: str = ""
    tier: str = ""
    model: str = ""


class LLMSettings(BaseSettings):
    llm_config: dict[str, dict[str, LLMConfig]] = Field(alias="FINHUB_LLM", default={})
    llm_task_config: dict[str, LLMTaskConfig] = Field(alias="FINHUB_LLM_TASK", default={})
    model_config = SettingsConfigDict(
        env_file="ai_clients_config.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
    )


settings_llm = LLMSettings()


class FinHubProxySettings(BaseSettings):
    proxy_mode: Literal["None", "Redirect", "Forward"] = Field(default="None", alias="FINHUB_PROXY_MODE")
    url_web_crawl_node: str = Field(default="", alias="FINHUB_URL_WEB_CRAWL_NODE")
    model_config = SettingsConfigDict(
        env_file="finhub_proxy_config.env",
        env_file_encoding="utf-8",
    )


settings_finhub_proxy = FinHubProxySettings()


class CompanyBriefInfo(BaseSettings):
    symbol: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    sector: Optional[str] = Field(default=None)
    market_cap: Optional[int] = Field(default=None)

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
