import os

import pytest

import server
from app import config


def _clear_environment(monkeypatch, *prefixes):
    for name in tuple(os.environ):
        if any(name.startswith(prefix) for prefix in prefixes):
            monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("raw_models", "expected"),
    [
        (" model-a, model-b, model-a, , ", {"model-a", "model-b"}),
        ("", set()),
    ],
)
def test_llm_models_decode_isolated_environment_configuration(monkeypatch, raw_models, expected):
    _clear_environment(monkeypatch, "MODELS", "FINHUB_LLM")
    monkeypatch.setenv("MODELS", raw_models)

    settings = config.LLMConfig(_env_file=None)

    assert settings.models == expected


def test_llm_vendor_settings_decode_only_the_supplied_nested_catalog(monkeypatch):
    _clear_environment(monkeypatch, "MODELS", "FINHUB_LLM")
    monkeypatch.setenv("FINHUB_LLM__TEST_VENDOR__PRIMARY__MODELS", " model-a, model-b, model-a ")
    monkeypatch.setenv("FINHUB_LLM__TEST_VENDOR__DISABLED__MODELS", "")

    settings = config.LLMVendorSettings(_env_file=None)

    assert set(settings.vendors) == {"test_vendor"}
    assert settings.vendors["test_vendor"]["primary"].models == {"model-a", "model-b"}
    assert settings.vendors["test_vendor"]["disabled"].models == set()


@pytest.mark.parametrize(
    ("raw_effort", "expected"),
    [
        (" high ", "High"),
        ("MEDIUM", "Medium"),
        ("low", "Low"),
        ("", None),
        (None, None),
    ],
)
def test_task_reasoning_effort_normalizes_isolated_values(raw_effort, expected):
    settings = config.LLMTaskConfig(reasoning_effort=raw_effort)

    assert settings.reasoning_effort == expected


@pytest.mark.parametrize(
    ("raw_mode", "expected"),
    [
        (None, "Standard"),
        ("economy", "Economy"),
        (" ECONOMY ", "Economy"),
        ("Standard", "Standard"),
        ("unsupported-mode", "Standard"),
        ("", "Standard"),
    ],
)
def test_tokenomics_mode_normalizes_isolated_environment_values(monkeypatch, raw_mode, expected):
    _clear_environment(monkeypatch, "FINHUB_LLM_TOKENOMICS_MODE", "FINHUB_LLM_TASK")
    if raw_mode is not None:
        monkeypatch.setenv("FINHUB_LLM_TOKENOMICS_MODE", raw_mode)

    settings = config.LLMTaskSettings(_env_file=None)

    assert settings.tokenomics_mode == expected


def test_constructor_values_override_the_isolated_process_environment(monkeypatch):
    _clear_environment(monkeypatch, "FINHUB_LLM_TOKENOMICS_MODE", "FINHUB_LLM_TASK")
    monkeypatch.setenv("FINHUB_LLM_TOKENOMICS_MODE", "economy")

    settings = config.LLMTaskSettings(FINHUB_LLM_TOKENOMICS_MODE="Standard", _env_file=None)

    assert settings.tokenomics_mode == "Standard"


def test_application_proxy_and_execution_settings_use_only_isolated_environment(monkeypatch):
    _clear_environment(
        monkeypatch,
        "FINHUB_API_KEY",
        "FINHUB_PROXY_MODE",
        "FINHUB_URL_",
        "FINHUB_OPENAI_EXECUTION_",
    )
    monkeypatch.setenv("FINHUB_API_KEY", "test-key")
    monkeypatch.setenv("FINHUB_PROXY_MODE", "Forward")
    monkeypatch.setenv("FINHUB_URL_WEB_CRAWL_NODE", "https://crawl.invalid")
    monkeypatch.setenv("FINHUB_URL_AI_TASK_NODE", "https://ai.invalid")
    monkeypatch.setenv("FINHUB_OPENAI_EXECUTION_MAX_CONCURRENT_REQUESTS", "3")
    monkeypatch.setenv("FINHUB_OPENAI_EXECUTION_RATE_LIMIT_MAX_WAIT_SECONDS", "45")

    app_settings = config.AppSettings(_env_file=None)
    proxy_settings = config.FinHubProxySettings(_env_file=None)
    execution_settings = config.OpenAIExecutionSettings(_env_file=None)

    assert app_settings.api_key == "test-key"
    assert proxy_settings.model_dump() == {
        "proxy_mode": "Forward",
        "url_web_crawl_node": "https://crawl.invalid",
        "url_ai_task_node": "https://ai.invalid",
    }
    assert execution_settings.max_concurrent_requests == 3
    assert execution_settings.rate_limit_max_wait_seconds == 45


class _ConfiguredFactory(config.LLMClientFactory):
    def __init__(self, value):
        self.value = value

    def create_gemini_client(self):
        return ("gemini", self.value)

    def create_openai_client(self):
        return ("openai", self.value)

    def create_azure_openai_client(self):
        return ("azure", self.value)

    def create_openrouter_client(self):
        return ("openrouter", self.value)


@pytest.mark.parametrize(
    ("vendor", "factory_key", "expected_provider"),
    [
        (" gemini ", "GEMINI", "gemini"),
        ("openai", "OPENAI", "openai"),
        ("Azure OpenAI", "AZURE_OPENAI", "azure"),
        ("azure_openai", "AZURE_OPENAI", "azure"),
        ("Open Router", "OPEN_ROUTER", "openrouter"),
        ("openrouter", "OPEN_ROUTER", "openrouter"),
    ],
)
def test_get_llm_client_resolves_documented_vendor_aliases(vendor, factory_key, expected_provider):
    settings = config.LLMVendorSettings(_env_file=None)
    settings.client_factories = {factory_key: {"PRIMARY": _ConfiguredFactory("client")}}

    client = settings.get_llm_client(vendor, " primary ")

    assert client == (expected_provider, "client")


def test_get_llm_client_returns_none_for_unconfigured_vendor_or_tier():
    settings = config.LLMVendorSettings(_env_file=None)
    settings.client_factories = {"OPENAI": {"PRIMARY": _ConfiguredFactory("client")}}

    assert settings.get_llm_client("unknown", "primary") is None
    assert settings.get_llm_client("openai", "missing") is None


def test_base_client_factory_is_an_instantiable_unsupported_provider_fallback():
    factory = config.LLMClientFactory()

    assert factory.create_gemini_client() is None
    assert factory.create_openai_client() is None
    assert factory.create_azure_openai_client() is None
    assert factory.create_openrouter_client() is None


class _FakeClient:
    def __init__(self, **options):
        self.options = options


def test_provider_factories_return_configured_reusable_clients(monkeypatch):
    monkeypatch.setattr(config.genai, "Client", _FakeClient)
    monkeypatch.setattr(config.openai, "AsyncOpenAI", _FakeClient)

    gemini_factory = config.GeminiClientFactory(api_key="gemini-key", timeout_sec=0)
    openai_factory = config.OpenAIClientFactory(api_key="openai-key", timeout_sec=12)
    openrouter_factory = config.OpenRouterClientFactory(
        endpoint="https://router.invalid/v1",
        api_key="router-key",
        timeout_sec=0,
    )
    gemini = gemini_factory.create_gemini_client()
    openai_client = openai_factory.create_openai_client()
    openrouter = openrouter_factory.create_openrouter_client()

    assert gemini.options["api_key"] == "gemini-key"
    assert gemini.options["http_options"].timeout == 30_000
    assert gemini_factory.create_gemini_client() is gemini
    assert openai_client.options == {
        "api_key": "openai-key",
        "project": "FinHub",
        "timeout": 12,
    }
    assert openai_factory.create_openai_client() is openai_client
    assert openrouter.options == {
        "api_key": "router-key",
        "base_url": "https://router.invalid/v1",
        "project": "FinHub",
        "timeout": 30,
    }
    assert openrouter_factory.create_openrouter_client() is openrouter


def test_azure_factory_creates_first_client_and_refreshes_after_thirty_minutes(monkeypatch):
    now = [10_000.0]
    monkeypatch.setattr(config.time, "time", lambda: now[0])
    monkeypatch.setattr(config, "EnvironmentCredential", lambda: object())
    monkeypatch.setattr(
        config,
        "get_bearer_token_provider",
        lambda credential, scope: lambda: f"token:{scope}",
    )
    monkeypatch.setattr(config.openai, "AsyncOpenAI", _FakeClient)
    factory = config.AzureOpenAIClientFactory(endpoint="https://azure.invalid", timeout_sec=0)

    first = factory.create_azure_openai_client()
    now[0] += 1_800
    retained = factory.create_azure_openai_client()
    now[0] += 1
    refreshed = factory.create_azure_openai_client()

    assert first is retained
    assert refreshed is not first
    assert refreshed.options == {
        "api_key": "token:https://ai.azure.com/.default",
        "base_url": "https://azure.invalid",
        "project": "FinHub",
        "timeout": 30,
    }


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, 8000),
        ("", 8000),
        ("not-a-port", 8000),
        ("0", 8000),
        ("-1", 8000),
        (" 9000 ", 9000),
    ],
)
def test_listen_port_uses_positive_integers_and_falls_back_otherwise(raw_value, expected):
    assert server.resolve_listen_port(raw_value) == expected
