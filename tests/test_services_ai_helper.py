import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from google.genai import types as genai_types

from app import config
from app.services import ai_helper


def _make_openai_response():
    return SimpleNamespace(
        output_text="ok",
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


def _make_gemini_response():
    return SimpleNamespace(
        text="ok",
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


class TestLlmTaskConfig:
    def test_reasoning_and_web_search_defaults(self):
        task_cfg = config.LLMTaskConfig()

        assert task_cfg.reasoning_effort is None
        assert task_cfg.use_web_search is False
        assert not hasattr(task_cfg, "temperature")

    def test_reasoning_effort_is_case_insensitive(self):
        task_cfg = config.LLMTaskConfig(reasoning_effort="High")

        assert task_cfg.reasoning_effort == "High"

    def test_underwritten_listing_tasks_use_terra_with_high_reasoning(self):
        settings = config.LLMTaskSettings()
        research_task = settings.tasks["asx_listtings_underwritten_research"]
        analysis_task = settings.tasks["asx_listtings_underwritten_analyze"]

        assert (research_task.model, research_task.reasoning_effort, research_task.use_web_search) == (
            "gpt-5.6-terra",
            "High",
            True,
        )
        assert (analysis_task.model, analysis_task.reasoning_effort, analysis_task.use_web_search) == (
            "gpt-5.6-terra",
            "High",
            False,
        )

    def test_dividend_tasks_split_web_research_from_assessment(self):
        settings = config.LLMTaskSettings()
        research_task = settings.tasks["analyze_div_event_research"]
        assessment_task = settings.tasks["analyze_div_event_assess"]

        assert (research_task.model, research_task.reasoning_effort, research_task.use_web_search) == (
            "gpt-5.6-terra",
            "High",
            True,
        )
        assert (assessment_task.model, assessment_task.reasoning_effort, assessment_task.use_web_search) == (
            "gpt-5.6-terra",
            "High",
            False,
        )


class TestAiExecPrompt:
    def test_ai_exec_prompt_uses_openai_path(self):
        task_cfg = config.LLMTaskConfig(task_name="demo", vendor="OPENAI", tier="cheap", model="gpt-4o-mini")
        expected = SimpleNamespace()

        with patch("app.services.ai_helper._exec_prompt_openai", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = expected

            result = asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "hello world"))

        assert result is expected
        mock_exec.assert_awaited_once_with(
            task_cfg,
            "hello world",
            country="",
            response_json_schema=None,
            schema_name="json_responses",
        )

    def test_ai_exec_prompt_raises_for_unknown_vendor(self):
        task_cfg = config.LLMTaskConfig(task_name="demo", vendor="UNKNOWN", tier="cheap", model="x")

        try:
            asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "hello"))
        except ValueError as exc:
            assert "Unsupported LLM vendor" in str(exc)
        else:
            raise AssertionError("Expected ValueError for unsupported vendor")


class TestAiExecTask:
    def test_ai_exec_task_builds_prompt_config_and_uses_task(self):
        task_cfg = config.LLMTaskConfig(
            task_name="demo",
            vendor="OPENAI",
            tier="cheap",
            model="gpt-5-mini",
            reasoning_effort="HIGH",
            use_web_search=True,
        )
        fake_settings = MagicMock()
        fake_settings.tasks = {"DEMO": task_cfg}

        with (
            patch("app.services.ai_helper.config.settings_llm_task", fake_settings),
            patch("app.services.ai_helper.ai_exec_prompt", new_callable=AsyncMock) as mock_exec_prompt,
        ):
            mock_exec_prompt.return_value = "ok"

            result = asyncio.run(ai_helper.ai_exec_task("DEMO", "prompt", country="AU"))

        assert result == "ok"
        mock_exec_prompt.assert_awaited_once()
        called_task_cfg, called_prompt = mock_exec_prompt.await_args.args
        assert called_task_cfg is task_cfg
        assert called_prompt == "prompt"
        assert called_task_cfg.reasoning_effort == "High"
        assert called_task_cfg.use_web_search is True
        assert mock_exec_prompt.await_args.kwargs == {
            "country": "AU",
            "response_json_schema": None,
            "schema_name": "json_responses",
        }

    def test_country_is_keyword_only(self):
        country_param = inspect.signature(ai_helper.ai_exec_task).parameters["country"]

        assert country_param.kind is inspect.Parameter.KEYWORD_ONLY


class TestExecPromptOpenAiClient:
    def test_responses_collects_provider_url_citations(self):
        task_cfg = config.LLMTaskConfig(vendor="OPENAI", model="gpt-5", use_web_search=True)
        client = MagicMock()
        response = _make_openai_response()
        response.output = [
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                url="https://www.asx.com.au/source",
                            ),
                            SimpleNamespace(
                                type="url_citation",
                                url="https://www.asx.com.au/source",
                            ),
                        ]
                    )
                ]
            )
        ]
        client.responses.create = AsyncMock(return_value=response)

        result = asyncio.run(
            ai_helper._exec_prompt_openai_client(
                client,
                task_cfg,
                "prompt",
                schema_name="json_responses",
            )
        )

        assert result.citation_urls == ["https://www.asx.com.au/source"]

    def test_responses_uses_model_defaults_when_reasoning_effort_is_missing(self):
        task_cfg = config.LLMTaskConfig(vendor="OPENAI", model="gpt-5-mini")
        client = MagicMock()
        client.responses.create = AsyncMock(return_value=_make_openai_response())

        result = asyncio.run(
            ai_helper._exec_prompt_openai_client(
                client,
                task_cfg,
                "prompt",
                schema_name="json_responses",
            )
        )

        assert result.completion == "ok"
        assert result.tokens_thought == 2
        assert result.tokens_cache == 3
        request_kwargs = client.responses.create.await_args.kwargs
        assert "reasoning" not in request_kwargs
        assert "temperature" not in request_kwargs

    def test_responses_uses_configured_reasoning_effort(self):
        task_cfg = config.LLMTaskConfig(vendor="OPENAI", model="gpt-5-mini", reasoning_effort="Medium")
        client = MagicMock()
        client.responses.create = AsyncMock(return_value=_make_openai_response())

        asyncio.run(
            ai_helper._exec_prompt_openai_client(
                client,
                task_cfg,
                "prompt",
                schema_name="json_responses",
            )
        )

        request_kwargs = client.responses.create.await_args.kwargs
        assert request_kwargs["reasoning"] == {"effort": "medium"}
        assert "temperature" not in request_kwargs

    def test_web_search_uses_task_config_and_country(self):
        task_cfg = config.LLMTaskConfig(
            vendor="OPENAI",
            model="gpt-5",
            reasoning_effort="High",
            use_web_search=True,
        )
        client = MagicMock()
        client.responses.create = AsyncMock(return_value=_make_openai_response())

        result = asyncio.run(
            ai_helper._exec_prompt_openai_client(
                client,
                task_cfg,
                "prompt",
                country="AU",
                schema_name="json_responses",
            )
        )

        assert result.completion == "ok"
        request_kwargs = client.responses.create.await_args.kwargs
        assert request_kwargs["reasoning"] == {"effort": "high"}
        assert request_kwargs["tools"][0]["user_location"] == {"type": "approximate", "country": "AU"}
        assert "temperature" not in request_kwargs
        client.chat.completions.create.assert_not_called()

    def test_web_search_omits_reasoning_when_missing(self):
        task_cfg = config.LLMTaskConfig(vendor="OPENAI", model="gpt-5", use_web_search=True)
        client = MagicMock()
        client.responses.create = AsyncMock(return_value=_make_openai_response())

        asyncio.run(
            ai_helper._exec_prompt_openai_client(
                client,
                task_cfg,
                "prompt",
                schema_name="json_responses",
            )
        )

        request_kwargs = client.responses.create.await_args.kwargs
        assert "reasoning" not in request_kwargs
        assert request_kwargs["tools"][0]["user_location"] is None
        assert "temperature" not in request_kwargs

    def test_structured_response_uses_schema_name(self):
        task_cfg = config.LLMTaskConfig(vendor="OPENAI", model="gpt-5-mini")
        client = MagicMock()
        client.responses.create = AsyncMock(return_value=_make_openai_response())
        response_schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

        asyncio.run(
            ai_helper._exec_prompt_openai_client(
                client,
                task_cfg,
                "prompt",
                response_json_schema=response_schema,
                schema_name="json_responses",
            )
        )

        response_format = client.responses.create.await_args.kwargs["text"]["format"]
        assert response_format["name"] == "json_responses"
        assert response_format["schema"] == response_schema

    def test_structured_response_removes_only_unsupported_string_formats(self):
        task_cfg = config.LLMTaskConfig(vendor="OPENAI", model="gpt-5-mini")
        client = MagicMock()
        client.responses.create = AsyncMock(return_value=_make_openai_response())
        response_schema = {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "minLength": 1,
                },
                "accessed_at": {
                    "type": "string",
                    "format": "date-time",
                },
                "format": {
                    "type": "string",
                },
            },
        }

        asyncio.run(
            ai_helper._exec_prompt_openai_client(
                client,
                task_cfg,
                "prompt",
                response_json_schema=response_schema,
                schema_name="json_responses",
            )
        )

        sent_schema = client.responses.create.await_args.kwargs["text"]["format"]["schema"]
        assert sent_schema["properties"]["url"] == {
            "type": "string",
            "minLength": 1,
        }
        assert sent_schema["properties"]["accessed_at"]["format"] == "date-time"
        assert "format" in sent_schema["properties"]
        assert response_schema["properties"]["url"]["format"] == "uri"


class TestExecPromptGemini:
    def test_uses_model_defaults_when_optional_config_is_missing(self):
        task_cfg = config.LLMTaskConfig(vendor="GEMINI", tier="cheap", model="gemini-3-flash")
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(return_value=_make_gemini_response())

        with patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client):
            result = asyncio.run(ai_helper._exec_prompt_gemini(task_cfg, "prompt"))

        assert result.completion == "ok"
        request_kwargs = client.aio.models.generate_content.await_args.kwargs
        generation_cfg = request_kwargs["config"]
        assert generation_cfg.thinking_config is None
        assert generation_cfg.tools is None

    def test_uses_configured_reasoning_and_web_search(self):
        task_cfg = config.LLMTaskConfig(
            vendor="GEMINI",
            tier="cheap",
            model="gemini-3-flash",
            reasoning_effort="LOW",
            use_web_search=True,
        )
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(return_value=_make_gemini_response())

        with patch.object(ai_helper.config.LLMVendorSettings, "get_llm_client", return_value=client):
            asyncio.run(ai_helper._exec_prompt_gemini(task_cfg, "prompt"))

        generation_cfg = client.aio.models.generate_content.await_args.kwargs["config"]
        assert generation_cfg.thinking_config.thinking_level == genai_types.ThinkingLevel.LOW
        assert generation_cfg.tools[0].google_search is not None
        assert generation_cfg.temperature is None
