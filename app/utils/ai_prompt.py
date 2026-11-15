"""Shared loading for source-controlled AI prompt templates."""

import functools
import re
from collections.abc import Mapping
from pathlib import Path

__all__ = ["PromptLoadError", "load_prompt", "render_prompt"]

_PROMPT_DIRECTORY = (Path(__file__).resolve().parents[2] / "resources" / "prompts").resolve()
_PROMPT_PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


class PromptLoadError(RuntimeError):
    pass


def load_prompt(file_name: str) -> str:
    """Load an application-managed prompt template for an AI workflow.

    Args:
        file_name: The file name or relative path under the project's
            ``resources/prompts`` directory.

    Returns:
        The non-empty prompt text with surrounding whitespace removed.

    Raises:
        PromptLoadError: If the file name is invalid, the file cannot be
            loaded, or its content is empty.

    Notes:
        Prompt files must remain within the ``resources/prompts`` directory.
    """
    normalized_name = file_name.strip()
    if not normalized_name:
        raise PromptLoadError("Prompt file name is required")

    prompt_path = (_PROMPT_DIRECTORY / normalized_name).resolve()
    try:
        prompt_path.relative_to(_PROMPT_DIRECTORY)
    except ValueError as exc:
        raise PromptLoadError(f"Prompt path '{file_name}' is outside the prompt directory") from exc
    return _load_prompt_content(prompt_path)


def render_prompt(
    file_name: str,
    replacements: Mapping[str, str],
) -> str:
    """Render an AI prompt template with task-specific values.

    Args:
        file_name: The file name or relative path under the project's
            ``resources/prompts`` directory.
        replacements: Text values keyed by placeholder name. The keys must
            exactly match all ``{{NAME}}`` placeholders declared by the template.

    Returns:
        The rendered prompt text.

    Raises:
        PromptLoadError: If the template cannot be loaded or the replacement
            names do not exactly match its placeholders.

    Notes:
        Replacement text is inserted literally and is not interpreted as
        another placeholder.
    """
    prompt = load_prompt(file_name)
    placeholders = set(_PROMPT_PLACEHOLDER_PATTERN.findall(prompt))
    replacement_names = set(replacements)
    if placeholders != replacement_names:
        missing = ", ".join(sorted(placeholders - replacement_names)) or "none"
        unexpected = ", ".join(sorted(replacement_names - placeholders)) or "none"
        raise PromptLoadError(
            f"Prompt '{file_name}' placeholders do not match replacements "
            f"(missing: {missing}; unexpected: {unexpected})"
        )
    return _PROMPT_PLACEHOLDER_PATTERN.sub(
        lambda match: replacements[match.group(1)],
        prompt,
    )


@functools.cache
def _load_prompt_content(prompt_path: Path) -> str:
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptLoadError(f"Unable to load prompt '{prompt_path.name}'") from exc
    if not prompt:
        raise PromptLoadError(f"Prompt '{prompt_path.name}' is empty")
    return prompt
