import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app import config
from app.services import ai_helper


class TestAiExecPrompt:
    def test_ai_exec_prompt_uses_openai_path(self):
        task_cfg = config.LLMTaskConfig(task_name="demo", vendor="OPENAI", tier="cheap", model="gpt-4o-mini")
        expected = SimpleNamespace()

        with patch("app.services.ai_helper._exec_prompt_openai", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = expected

            result = asyncio.run(ai_helper.ai_exec_prompt(task_cfg, "hello world"))

        assert result is expected
        mock_exec.assert_awaited_once_with(task_cfg, "hello world", None, 0.2)

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
        task_cfg = config.LLMTaskConfig(task_name="demo", vendor="OPENAI", tier="cheap", model="gpt-5-mini")
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
        called_task_cfg, called_prompt, called_cfg = mock_exec_prompt.await_args.args
        assert called_task_cfg is task_cfg
        assert called_prompt == "prompt"
        assert called_cfg.use_web_search is True
        assert called_cfg.country == "AU"
        assert mock_exec_prompt.await_args.kwargs["llm_config_override"] is None
