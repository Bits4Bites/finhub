import shutil
import uuid
from pathlib import Path

import pytest

from app.utils import ai_prompt as ai_prompt_utils

_PROMPT_DIRECTORY = Path(__file__).resolve().parents[1] / "resources" / "prompts"


@pytest.fixture
def prompt_file():
    test_directory = _PROMPT_DIRECTORY / f".pytest-{uuid.uuid4().hex}"

    def create(file_name: str, content: str | bytes) -> str:
        prompt_path = test_directory / file_name
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            prompt_path.write_bytes(content)
        else:
            prompt_path.write_text(content, encoding="utf-8")
        return str(prompt_path.relative_to(_PROMPT_DIRECTORY))

    yield create

    if test_directory.exists():
        shutil.rmtree(test_directory)


def test_load_prompt_returns_prompt_text(prompt_file):
    file_name = prompt_file(
        "analysis/overview.txt",
        "\n  Analyze {{SYMBOL}} for material financial events.  \n",
    )

    result = ai_prompt_utils.load_prompt(file_name)

    assert result == "Analyze {{SYMBOL}} for material financial events."


def test_load_prompt_rejects_empty_file_name():
    with pytest.raises(ai_prompt_utils.PromptLoadError):
        ai_prompt_utils.load_prompt("  ")


def test_load_prompt_rejects_path_outside_prompt_directory():
    with pytest.raises(ai_prompt_utils.PromptLoadError):
        ai_prompt_utils.load_prompt("../outside.txt")


def test_load_prompt_reports_missing_prompt():
    file_name = f".pytest-{uuid.uuid4().hex}/missing-prompt.txt"

    with pytest.raises(ai_prompt_utils.PromptLoadError):
        ai_prompt_utils.load_prompt(file_name)


def test_load_prompt_rejects_empty_prompt(prompt_file):
    file_name = prompt_file("empty-prompt.txt", " \n ")

    with pytest.raises(ai_prompt_utils.PromptLoadError):
        ai_prompt_utils.load_prompt(file_name)


def test_load_prompt_reports_invalid_utf8_as_a_loading_error(prompt_file):
    file_name = prompt_file("invalid-utf8.txt", b"\xff\xfe\xfa")

    with pytest.raises(ai_prompt_utils.PromptLoadError):
        ai_prompt_utils.load_prompt(file_name)


def test_render_prompt_replaces_all_declared_placeholders(prompt_file):
    file_name = prompt_file(
        "ticker/research.txt",
        "Analyze {{SYMBOL}} on {{EXCHANGE}}. Recheck {{SYMBOL}}.",
    )

    result = ai_prompt_utils.render_prompt(
        file_name,
        {
            "SYMBOL": "AAPL",
            "EXCHANGE": "NASDAQ",
        },
    )

    assert result == "Analyze AAPL on NASDAQ. Recheck AAPL."


def test_render_prompt_supports_templates_without_placeholders(prompt_file):
    file_name = prompt_file("market-summary.txt", "Summarize current market conditions.")

    result = ai_prompt_utils.render_prompt(file_name, {})

    assert result == "Summarize current market conditions."


def test_render_prompt_inserts_replacement_text_literally(prompt_file):
    file_name = prompt_file("literal.txt", "{{FIRST}} / {{SECOND}}")

    result = ai_prompt_utils.render_prompt(
        file_name,
        {
            "FIRST": "{{SECOND}}",
            "SECOND": "trusted",
        },
    )

    assert result == "{{SECOND}} / trusted"


def test_render_prompt_propagates_prompt_loading_errors():
    file_name = f".pytest-{uuid.uuid4().hex}/missing-prompt.txt"

    with pytest.raises(ai_prompt_utils.PromptLoadError):
        ai_prompt_utils.render_prompt(file_name, {})


@pytest.mark.parametrize(
    "replacements",
    [
        {},
        {"SYMBOL": "AAPL", "UNEXPECTED": "value"},
    ],
)
def test_render_prompt_rejects_placeholder_mismatch(prompt_file, replacements):
    file_name = prompt_file("research.txt", "Analyze {{SYMBOL}}.")

    with pytest.raises(ai_prompt_utils.PromptLoadError):
        ai_prompt_utils.render_prompt(file_name, replacements)
