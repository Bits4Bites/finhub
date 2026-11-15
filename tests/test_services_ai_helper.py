import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest
from pydantic import BaseModel, ValidationError

from app import config
from app.services import ai_helper


def _openai_response() -> SimpleNamespace:
    return SimpleNamespace(
        output_text="provider response",
        status="completed",
        output=[],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            total_tokens=17,
            input_tokens_details=SimpleNamespace(cached_tokens=3),
            output_tokens_details=SimpleNamespace(reasoning_tokens=2),
        ),
    )


def _openrouter_response() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="provider response"))],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=17,
            prompt_tokens_details=SimpleNamespace(cached_tokens=3),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=2),
        ),
    )


def _gemini_response() -> SimpleNamespace:
    return SimpleNamespace(
        text="provider response",
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
            thoughts_token_count=2,
            tool_use_prompt_token_count=1,
            cached_content_token_count=3,
            total_token_count=17,
        ),
        prompt_feedback=None,
        candidates=[SimpleNamespace()],
    )


def _provider_client(api: str) -> MagicMock:
    client = MagicMock()
    if api == "responses":
        client.responses.create = AsyncMock(return_value=_openai_response())
    elif api == "chat":
        client.chat.completions.create = AsyncMock(return_value=_openrouter_response())
    else:
        client.aio.models.generate_content = AsyncMock(return_value=_gemini_response())
    return client


def _rate_limit_error(*, code: str = "rate_limit_exceeded") -> openai.RateLimitError:
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    return openai.RateLimitError(
        "sensitive provider message",
        response=response,
        body={"error": {"type": "too_many_requests", "code": code}},
    )


def test_structured_validation_logging_omits_rejected_values_and_messages(caplog):
    class ExampleModel(BaseModel):
        value: int

    with pytest.raises(ValidationError) as error_info:
        ExampleModel.model_validate({"value": "private rejected value"})

    result = ai_helper.log_structured_validation_failure(
        "Ticker Analysis",
        "Forecast",
        error_info.value,
    )

    assert result is None
    assert "Ticker Analysis" in caplog.text
    assert "Forecast" in caplog.text
    assert "1 validation error(s): int_parsing" in caplog.text
    assert "value" not in caplog.text
    assert "private rejected value" not in caplog.text
    assert "Input should be" not in caplog.text


def test_structured_validation_logging_omits_generic_exception_values(caplog):
    ai_helper.log_structured_validation_failure(
        "US Listings",
        "Assessment",
        ValueError("api-key=private-sensitive-value"),
    )

    assert "ValueError" in caplog.text
    assert "private-sensitive-value" not in caplog.text
    assert "api-key" not in caplog.text


@pytest.mark.parametrize(
    ("vendor", "provider_name", "api"),
    [
        ("OPENAI", "OPENAI", "responses"),
        ("AZUREOPENAI", "AZURE_OPENAI", "responses"),
        ("azure openai", "AZURE_OPENAI", "responses"),
        ("Azure_OpenAI", "AZURE_OPENAI", "responses"),
        ("AZURE-OPENAI", "AZURE_OPENAI", "responses"),
        ("OPENROUTER", "OPEN_ROUTER", "chat"),
        ("open router", "OPEN_ROUTER", "chat"),
        ("Open_Router", "OPEN_ROUTER", "chat"),
        ("OPEN-ROUTER", "OPEN_ROUTER", "chat"),
        ("gemini", "GEMINI", "gemini"),
    ],
)
def test_ai_exec_prompt_supports_documented_vendor_aliases(vendor, provider_name, api):
    task_cfg = config.LLMTaskConfig(
        task_name="documented task",
        vendor=vendor,
        tier="cheap",
        model="provider-model",
    )
    client = _provider_client(api)

    with patch.object(
        ai_helper.config.LLMVendorSettings,
        "get_llm_client",
        return_value=client,
    ) as get_client:
        result = asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "Analyze this event."))

    assert isinstance(result, ai_helper.LLMResponse)
    assert result.is_error is False
    assert result.completion == "provider response"
    assert result.tokens_total == 17
    get_client.assert_called_once_with(provider_name, "cheap")


def test_ai_exec_task_uses_exact_task_lookup_and_returns_llm_response():
    task_cfg = config.LLMTaskConfig(
        task_name="configured task",
        vendor="OPENAI",
        tier="cheap",
        model="gpt-test",
        use_web_search=True,
    )
    task_settings = SimpleNamespace(tasks={"ANALYZE_EVENT": task_cfg})
    client = _provider_client("responses")
    response_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    with (
        patch.object(ai_helper.config, "settings_llm_task", task_settings),
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            ai_helper.ai_exec_task(
                "ANALYZE_EVENT",
                "Analyze this event.",
                country="AU",
                response_json_schema=response_schema,
                schema_name="event_analysis",
            )
        )

    assert isinstance(result, ai_helper.LLMResponse)
    assert result.completion == "provider response"
    request = client.responses.create.await_args.kwargs
    assert request["model"] == "gpt-test"
    assert request["input"] == "Analyze this event."
    assert request["tools"][0]["user_location"]["country"] == "AU"
    assert request["text"]["format"]["name"] == "event_analysis"
    assert request["text"]["format"]["schema"] == response_schema


def test_ai_exec_task_rejects_missing_or_differently_cased_task_id():
    task_settings = SimpleNamespace(tasks={"ANALYZE_EVENT": config.LLMTaskConfig(vendor="OPENAI")})

    with (
        patch.object(ai_helper.config, "settings_llm_task", task_settings),
        pytest.raises(ValueError, match="task_id 'analyze_event' not found"),
    ):
        asyncio.run(ai_helper.ai_exec_task("analyze_event", "prompt"))


def test_ai_exec_prompt_rejects_unsupported_vendor():
    task_cfg = config.LLMTaskConfig(vendor="UNKNOWN", tier="cheap", model="model")

    with pytest.raises(ValueError, match="Unsupported LLM vendor: UNKNOWN"):
        asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "prompt"))


def test_ai_exec_prompt_reports_missing_provider_configuration():
    task_cfg = config.LLMTaskConfig(vendor="OPENAI", tier="unconfigured", model="model")

    with (
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=None,
        ),
        pytest.raises(OSError, match="OpenAI client for tier 'unconfigured' is not configured"),
    ):
        asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "prompt"))


def test_ai_exec_prompt_propagates_provider_failures():
    task_cfg = config.LLMTaskConfig(vendor="OPENAI", tier="cheap", model="model")
    client = _provider_client("responses")
    client.responses.create.side_effect = RuntimeError("provider connection failed")

    with (
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=client,
        ),
        pytest.raises(RuntimeError, match="provider connection failed"),
    ):
        asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "prompt"))


def test_ai_exec_prompt_raises_after_retryable_rate_limit_budget_is_exhausted():
    task_cfg = config.LLMTaskConfig(vendor="OPENAI", tier="cheap", model="model")
    client = _provider_client("responses")
    client.responses.create.side_effect = _rate_limit_error()

    with (
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=client,
        ),
        patch.object(
            ai_helper.config.settings_openai_execution,
            "rate_limit_max_wait_seconds",
            0,
        ),
        pytest.raises(ai_helper.LLMRateLimitError, match="remained rate limited"),
    ):
        asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "prompt"))


def test_ai_exec_prompt_propagates_non_retryable_quota_limit():
    task_cfg = config.LLMTaskConfig(vendor="OPENAI", tier="cheap", model="model")
    client = _provider_client("responses")
    error = _rate_limit_error(code="insufficient_quota")
    client.responses.create.side_effect = error

    with (
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=client,
        ),
        pytest.raises(openai.RateLimitError) as error_info,
    ):
        asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "prompt"))

    assert error_info.value is error
