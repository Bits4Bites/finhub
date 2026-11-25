import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pydantic
import pytest
from openai.types import responses
from pydantic import BaseModel, ValidationError

from app import config
from app.services import ai_helper

_CITATION_URL = "https://example.com/research"


def _openai_response(
    *,
    status: str = "completed",
    text: str = "provider response",
) -> SimpleNamespace:
    return SimpleNamespace(
        output_text=text,
        status=status,
        output=[
            {
                "type": "message",
                "content": [
                    {"type": "url_citation", "url": _CITATION_URL},
                    {"type": "url_citation", "url": _CITATION_URL},
                ],
            }
        ],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            total_tokens=17,
            input_tokens_details=SimpleNamespace(cached_tokens=3),
            output_tokens_details=SimpleNamespace(reasoning_tokens=2),
        ),
    )


def _openrouter_response(
    *,
    text: str | None = "provider response",
) -> SimpleNamespace:
    choices = [] if text is None else [SimpleNamespace(message=SimpleNamespace(content=text))]
    return SimpleNamespace(
        choices=choices,
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=17,
            prompt_tokens_details=SimpleNamespace(cached_tokens=3),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=2),
        ),
    )


def _gemini_response(
    *,
    text: str = "provider response",
    blocked: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
            thoughts_token_count=2,
            tool_use_prompt_token_count=1,
            cached_content_token_count=3,
            total_token_count=17,
        ),
        prompt_feedback=SimpleNamespace(block_reason="SAFETY") if blocked else None,
        candidates=[] if blocked else [SimpleNamespace()],
    )


def _provider_client(api: str, response: object | None = None) -> MagicMock:
    client = MagicMock()
    if api == "responses":
        client.responses.create = AsyncMock(return_value=response or _openai_response())
    elif api == "chat":
        client.chat.completions.create = AsyncMock(return_value=response or _openrouter_response())
    else:
        client.aio.models.generate_content = AsyncMock(return_value=response or _gemini_response())
    return client


def _rate_limit_error(*, code: str = "rate_limit_exceeded") -> openai.RateLimitError:
    response = httpx.Response(
        429,
        headers={"retry-after": "0"},
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    return openai.RateLimitError(
        "provider rate limit",
        response=response,
        body={"error": {"type": "too_many_requests", "code": code}},
    )


def _task_config(vendor: str) -> config.LLMTaskConfig:
    return config.LLMTaskConfig(
        task_name="documented task",
        vendor=vendor,
        tier="standard",
        model="provider-model",
    )


def test_structured_validation_logging_excludes_rejected_values_and_messages(caplog):
    class ExampleModel(BaseModel):
        value: int

    with pytest.raises(ValidationError) as error_info:
        ExampleModel.model_validate({"value": "private rejected value"})

    ai_helper.log_structured_validation_failure(
        "Ticker Analysis",
        "Forecast",
        error_info.value,
    )

    assert "Ticker Analysis" in caplog.text
    assert "Forecast" in caplog.text
    assert "int_parsing" in caplog.text
    assert "private rejected value" not in caplog.text
    assert "Input should be" not in caplog.text


def test_structured_validation_logging_for_generic_error_only_exposes_error_type(caplog):
    ai_helper.log_structured_validation_failure(
        "US Listings",
        "Assessment",
        ValueError("api-key=private-sensitive-value"),
    )

    assert "ValueError" in caplog.text
    assert "private-sensitive-value" not in caplog.text
    assert "api-key" not in caplog.text


def test_structured_validation_logging_reports_schema_fields_and_limits_without_input_keys(caplog):
    class Source(BaseModel):
        title: str = pydantic.Field(max_length=5)

    class ExampleModel(BaseModel):
        references: list[Source]
        sources_by_name: dict[str, Source]

    with pytest.raises(ValidationError) as error_info:
        ExampleModel.model_validate(
            {
                "references": [{"title": "private source title"}],
                "sources_by_name": {"private dictionary key": {"title": "private source title"}},
            }
        )

    ai_helper.log_structured_validation_failure(
        "Portfolio Spotlight",
        "Research",
        error_info.value,
        response_model=ExampleModel,
    )

    assert "references[*].title: string_too_long (max_length=5)" in caplog.text
    assert "sources_by_name.<field>.title: string_too_long (max_length=5)" in caplog.text
    assert "private" not in caplog.text
    assert "String should have" not in caplog.text


def test_structured_validation_logging_redacts_unknown_extra_field_names(caplog):
    class ExampleModel(BaseModel):
        model_config = pydantic.ConfigDict(extra="forbid")
        value: int

    with pytest.raises(ValidationError) as error_info:
        ExampleModel.model_validate({"value": 1, "private unexpected property": "private value"})

    ai_helper.log_structured_validation_failure(
        "Portfolio Spotlight",
        "Research",
        error_info.value,
        response_model=ExampleModel,
    )

    assert "<field>: extra_forbidden" in caplog.text
    assert "private" not in caplog.text


def test_structured_validation_logging_excludes_custom_validation_context(caplog):
    class ExampleModel(BaseModel):
        value: str

        @pydantic.field_validator("value")
        @classmethod
        def validate_value(cls, value: str) -> str:
            raise ValueError("private validation context")

    with pytest.raises(ValidationError) as error_info:
        ExampleModel.model_validate({"value": "private rejected value"})

    ai_helper.log_structured_validation_failure(
        "Portfolio Spotlight",
        "Research",
        error_info.value,
        response_model=ExampleModel,
    )

    assert "value: value_error" in caplog.text
    assert "private" not in caplog.text


@pytest.mark.parametrize(
    ("vendor", "api"),
    [
        ("OPENAI", "responses"),
        ("AZUREOPENAI", "responses"),
        ("azure openai", "responses"),
        ("Azure_OpenAI", "responses"),
        ("AZURE-OPENAI", "responses"),
        ("OPENROUTER", "chat"),
        ("open router", "chat"),
        ("Open_Router", "chat"),
        ("OPEN-ROUTER", "chat"),
        ("gemini", "gemini"),
    ],
)
def test_ai_exec_prompt_accepts_documented_vendor_aliases(vendor, api):
    client = _provider_client(api)
    with patch.object(
        ai_helper.config.LLMVendorSettings,
        "get_llm_client",
        return_value=client,
    ):
        result = asyncio.run(ai_helper.ai_exec_prompt(_task_config(vendor), "Analyze this event."))

    assert result.completion == "provider response"
    assert result.is_error is False
    assert result.error_msg is None


@pytest.mark.parametrize(
    ("vendor", "api", "expected_tool_tokens", "expected_citations"),
    [
        ("OPENAI", "responses", 0, [_CITATION_URL]),
        ("OPENROUTER", "chat", 0, []),
        ("GEMINI", "gemini", 1, []),
    ],
)
def test_ai_exec_prompt_normalizes_provider_results(
    vendor,
    api,
    expected_tool_tokens,
    expected_citations,
):
    client = _provider_client(api)
    with patch.object(
        ai_helper.config.LLMVendorSettings,
        "get_llm_client",
        return_value=client,
    ):
        result = asyncio.run(ai_helper.ai_exec_prompt(_task_config(vendor), "Analyze this event."))

    assert result == ai_helper.LLMResponse(
        completion="provider response",
        time_taken_ms=result.time_taken_ms,
        tokens_prompt=10,
        tokens_completion=5,
        tokens_thought=2,
        tokens_tool=expected_tool_tokens,
        tokens_cache=3,
        tokens_total=17,
        citation_urls=expected_citations,
    )
    assert result.time_taken_ms >= 0


@pytest.mark.parametrize(
    ("vendor", "api", "response", "expected_completion", "expected_error"),
    [
        (
            "OPENAI",
            "responses",
            _openai_response(status="failed", text="request rejected"),
            "request rejected",
            "request rejected",
        ),
        (
            "OPENROUTER",
            "chat",
            _openrouter_response(text=None),
            "",
            None,
        ),
        (
            "GEMINI",
            "gemini",
            _gemini_response(text="request blocked", blocked=True),
            "request blocked",
            "request blocked",
        ),
    ],
)
def test_ai_exec_prompt_normalizes_provider_error_fields(
    vendor,
    api,
    response,
    expected_completion,
    expected_error,
):
    client = _provider_client(api, response)
    with patch.object(
        ai_helper.config.LLMVendorSettings,
        "get_llm_client",
        return_value=client,
    ):
        result = asyncio.run(ai_helper.ai_exec_prompt(_task_config(vendor), "Analyze this event."))

    assert result.is_error is True
    assert result.completion == expected_completion
    assert result.error_msg == expected_error


@pytest.mark.parametrize(
    ("status", "error", "incomplete_details"),
    [
        ("failed", {"code": "invalid_prompt", "message": "private provider error"}, None),
        ("incomplete", None, SimpleNamespace(reason="content_filter")),
    ],
)
def test_provider_diagnostics_expose_failure_metadata_without_portfolio_content(
    status, error, incomplete_details, monkeypatch, caplog, capsys
):
    monkeypatch.setenv("LLM_DEBUG_MODE", "false")
    response = _openai_response(status=status, text="private portfolio response")
    response.id = "resp-research"
    response._request_id = "req-research"
    response.error = error
    response.incomplete_details = incomplete_details
    response.output.append(
        SimpleNamespace(
            type="web_search_call",
            status="failed",
            action=SimpleNamespace(type="search", query="private investor query"),
        )
    )
    client = _provider_client("responses", response)
    with patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client):
        result = asyncio.run(ai_helper.ai_exec_prompt(_task_config("Azure OpenAI"), "private portfolio prompt"))

    diagnostic = next(record for record in caplog.records if "Provider diagnostics: " in record.message)
    details = json.loads(diagnostic.message.split("Provider diagnostics: ", 1)[1])
    assert diagnostic.levelno == logging.WARNING
    assert details["task"] == "documented task"
    assert details["vendor"] == "Azure OpenAI"
    assert details["model"] == "provider-model"
    assert details["response_id"] == "resp-research"
    assert details["request_id"] == "req-research"
    assert details["status"] == status
    assert details["error_code"] == ("invalid_prompt" if error else None)
    assert details["incomplete_reason"] == ("content_filter" if incomplete_details else None)
    assert details["output"][-1] == {
        "type": "web_search_call",
        "status": "failed",
        "action_type": "search",
        "content_types": [],
    }
    logged = caplog.text + capsys.readouterr().out
    assert "private" not in logged
    assert result.is_error is True
    assert result.completion == "private portfolio response"


@pytest.mark.parametrize("debug", [False, True])
def test_completed_refusal_is_logged_without_changing_result_handling(debug, monkeypatch, caplog, capsys):
    monkeypatch.setenv("LLM_DEBUG_MODE", str(debug))
    refusal = "I cannot assist with this private portfolio request."
    response = responses.Response.model_construct(
        id="resp-refusal",
        status="completed",
        usage=None,
        output=[
            responses.ResponseOutputMessage(
                id="msg-refusal",
                type="message",
                status="completed",
                role="assistant",
                content=[responses.ResponseOutputRefusal(type="refusal", refusal=refusal)],
            )
        ],
    )
    client = _provider_client("responses", response)
    with patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client):
        result = asyncio.run(ai_helper.ai_exec_prompt(_task_config("Azure OpenAI"), "private portfolio prompt"))

    diagnostic = next(record for record in caplog.records if "Provider diagnostics: " in record.message)
    details = json.loads(diagnostic.message.split("Provider diagnostics: ", 1)[1])
    assert diagnostic.levelno == logging.WARNING
    assert details["response_id"] == "resp-refusal"
    assert details["status"] == "completed"
    assert details["refusal_count"] == 1
    assert details["output"][0]["content_types"] == ["refusal"]
    assert ("refusals" in details) is debug
    if debug:
        assert details["refusals"] == [refusal]
    assert (refusal in caplog.text) is debug
    assert ("Raw provider response" in caplog.text) is debug
    if not debug:
        assert "private" not in caplog.text + capsys.readouterr().out
    assert result.is_error is False
    assert result.completion == ""


def test_chat_refusal_diagnostics_include_finish_reason_without_exposing_text(monkeypatch, caplog):
    monkeypatch.setenv("LLM_DEBUG_MODE", "false")
    response = _openrouter_response(text="")
    response.choices[0].finish_reason = "content_filter"
    response.choices[0].message.refusal = "private refusal explanation"
    client = _provider_client("chat", response)
    with patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client):
        result = asyncio.run(ai_helper.ai_exec_prompt(_task_config("OpenRouter"), "private portfolio prompt"))

    diagnostic = next(record for record in caplog.records if "Provider diagnostics: " in record.message)
    details = json.loads(diagnostic.message.split("Provider diagnostics: ", 1)[1])
    assert details["finish_reasons"] == ["content_filter"]
    assert details["refusal_count"] == 1
    assert "private" not in caplog.text
    assert result.is_error is False


@pytest.mark.parametrize("debug", [False, True])
def test_http_rejection_diagnostics_capture_azure_request_id_and_preserve_exception(debug, monkeypatch, caplog):
    monkeypatch.setenv("LLM_DEBUG_MODE", str(debug))
    failure = openai.BadRequestError(
        "private provider error",
        response=httpx.Response(
            400,
            headers={"apim-request-id": "azure-request"},
            request=httpx.Request("POST", "https://example.test/responses"),
        ),
        body={
            "error": {
                "code": "content_filter",
                "message": "private moderation explanation",
                "innererror": {"code": "ResponsibleAIPolicyViolation"},
            }
        },
    )
    client = _provider_client("responses")
    client.responses.create.side_effect = failure
    with (
        patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client),
        pytest.raises(openai.BadRequestError) as error_info,
    ):
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("Azure OpenAI"), "private portfolio prompt"))

    diagnostic = next(record for record in caplog.records if "Provider diagnostics: " in record.message)
    details = json.loads(diagnostic.message.split("Provider diagnostics: ", 1)[1])
    assert details["http_status"] == 400
    assert details["request_id"] == "azure-request"
    assert details["error_code"] == "content_filter"
    assert details["inner_error_code"] == "ResponsibleAIPolicyViolation"
    assert ("private moderation explanation" in caplog.text) is debug
    assert ("Raw provider response" in caplog.text) is debug
    if not debug:
        assert "private" not in caplog.text
    assert error_info.value is failure
    assert client.responses.create.await_count == 1


def test_success_diagnostics_exclude_response_text_and_debug_response_is_bounded(monkeypatch, caplog):
    response = _openai_response(text="private output " * 4000)
    client = _provider_client("responses", response)
    caplog.set_level(logging.INFO)
    with patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client):
        monkeypatch.setenv("LLM_DEBUG_MODE", "false")
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("OPENAI"), "private prompt"))
        assert "Provider diagnostics: " in caplog.text
        assert "private" not in caplog.text

        caplog.clear()
        monkeypatch.setenv("LLM_DEBUG_MODE", "true")
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("OPENAI"), "private prompt"))

    raw = next(record.message for record in caplog.records if "Raw provider response" in record.message)
    assert "private output" in raw
    assert raw.endswith("[truncated]")
    assert len(raw) < 33_000


def test_debug_diagnostics_preserve_refusal_reason_when_raw_response_is_truncated(monkeypatch, caplog):
    monkeypatch.setenv("LLM_DEBUG_MODE", "true")
    response = _openai_response(text="")
    refusal = "I cannot fulfill this request because of the provider's safety policy."
    response.output = [
        {"type": "reasoning", "summary": [{"text": "long research output " * 4000}]},
        {"type": "message", "content": [{"type": "refusal", "refusal": refusal}]},
    ]
    client = _provider_client("responses", response)
    with patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client):
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("Azure OpenAI"), "portfolio prompt"))

    diagnostic = next(record for record in caplog.records if "Provider diagnostics: " in record.message)
    details = json.loads(diagnostic.message.split("Provider diagnostics: ", 1)[1])
    assert details["refusals"] == [refusal]
    raw = next(record.message for record in caplog.records if "Raw provider response" in record.message)
    assert raw.endswith("[truncated]")
    assert refusal not in raw


def test_ai_exec_task_uses_exact_case_sensitive_configuration_lookup():
    expected = ai_helper.LLMResponse(completion="configured result")
    task_settings = SimpleNamespace(tasks={"ANALYZE_EVENT": _task_config("OPENAI")})

    with (
        patch.object(ai_helper.config, "settings_llm_task", task_settings),
        patch.object(ai_helper, "ai_exec_prompt", new_callable=AsyncMock, return_value=expected),
    ):
        result = asyncio.run(ai_helper.ai_exec_task("ANALYZE_EVENT", "Analyze this event."))
        with pytest.raises(ValueError):
            asyncio.run(ai_helper.ai_exec_task("analyze_event", "Analyze this event."))

    assert result == expected


def test_ai_exec_prompt_rejects_unsupported_vendor():
    with pytest.raises(ValueError):
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("UNKNOWN"), "prompt"))


def test_ai_exec_prompt_reports_missing_provider_configuration():
    with (
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=None,
        ),
        pytest.raises(OSError),
    ):
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("OPENAI"), "prompt"))


def test_ai_exec_prompt_propagates_provider_failure():
    failure = RuntimeError("provider connection failed")
    client = _provider_client("responses")
    client.responses.create.side_effect = failure

    with (
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=client,
        ),
        pytest.raises(RuntimeError) as error_info,
    ):
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("OPENAI"), "prompt"))

    assert error_info.value is failure


def test_ai_exec_prompt_recovers_from_retryable_rate_limit():
    client = _provider_client("responses")
    client.responses.create.side_effect = [_rate_limit_error(), _openai_response()]

    with patch.object(
        ai_helper.config.LLMVendorSettings,
        "get_llm_client",
        return_value=client,
    ):
        result = asyncio.run(ai_helper.ai_exec_prompt(_task_config("OPENAI"), "prompt"))

    assert result.is_error is False
    assert result.completion == "provider response"


def test_ai_exec_prompt_raises_after_retryable_rate_limit_budget_is_exhausted():
    rate_limit = _rate_limit_error()
    client = _provider_client("responses")
    client.responses.create.side_effect = rate_limit

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
        pytest.raises(ai_helper.LLMRateLimitError),
    ):
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("OPENAI"), "prompt"))


def test_ai_exec_prompt_propagates_non_retryable_quota_limit():
    quota_limit = _rate_limit_error(code="insufficient_quota")
    client = _provider_client("responses")
    client.responses.create.side_effect = quota_limit

    with (
        patch.object(
            ai_helper.config.LLMVendorSettings,
            "get_llm_client",
            return_value=client,
        ),
        pytest.raises(openai.RateLimitError) as error_info,
    ):
        asyncio.run(ai_helper.ai_exec_prompt(_task_config("OPENAI"), "prompt"))

    assert error_info.value is quota_limit
