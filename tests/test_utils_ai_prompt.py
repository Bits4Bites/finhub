from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils import ai_prompt as ai_prompt_utils


def test_load_prompt_strips_and_caches_content():
    with patch.object(Path, "read_text", return_value="\n  Prompt content  \n") as mock_read:
        first = ai_prompt_utils.load_prompt("cached-prompt.txt")
        second = ai_prompt_utils.load_prompt("cached-prompt.txt")

    assert first == "Prompt content"
    assert second == first
    mock_read.assert_called_once_with(encoding="utf-8")


def test_load_prompt_uses_normalized_path_as_cache_key():
    with patch.object(Path, "read_text", return_value="Prompt content") as mock_read:
        ai_prompt_utils.load_prompt("normalized-prompt.txt")
        ai_prompt_utils.load_prompt(str(Path(".") / "normalized-prompt.txt"))

    mock_read.assert_called_once_with(encoding="utf-8")


def test_load_prompt_rejects_path_outside_prompt_directory():
    outside_path = str(Path("..") / "outside.txt")

    with pytest.raises(ai_prompt_utils.PromptLoadError, match="outside the prompt directory"):
        ai_prompt_utils.load_prompt(outside_path)


def test_load_prompt_rejects_empty_file_name():
    with pytest.raises(ai_prompt_utils.PromptLoadError, match="file name is required"):
        ai_prompt_utils.load_prompt("  ")


def test_load_prompt_wraps_file_errors():
    with (
        patch.object(Path, "read_text", side_effect=OSError("disk failure")) as mock_read,
        pytest.raises(ai_prompt_utils.PromptLoadError, match="Unable to load prompt"),
    ):
        ai_prompt_utils.load_prompt("missing-prompt.txt")

    mock_read.assert_called_once_with(encoding="utf-8")


def test_load_prompt_rejects_empty_content_without_caching_failure():
    with patch.object(Path, "read_text", return_value="  ") as mock_read:
        for _ in range(2):
            with pytest.raises(ai_prompt_utils.PromptLoadError, match="is empty"):
                ai_prompt_utils.load_prompt("empty-prompt.txt")

    assert mock_read.call_count == 2
