from typing import Optional

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


class Settings(BaseSettings):
    llm_config: dict[str, dict[str, LLMConfig]] = Field(alias="FINHUB_LLM", default={})
    llm_task_config: dict[str, LLMTaskConfig] = Field(alias="FINHUB_LLM_TASK", default={})
    model_config = SettingsConfigDict(
        env_file="ai_clients_config.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
    )


settings = Settings()
