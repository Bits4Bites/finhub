def normalize_json_str(json_str: str) -> str:
    """Extract JSON text from an optional Markdown JSON code block.

    Args:
        json_str: JSON text, optionally wrapped in a complete Markdown code block
            with the lowercase ``json`` language label.

    Returns:
        The JSON text without its code-block markers or surrounding whitespace.
        Text without a complete supported code block is returned unchanged.

    Notes:
        The opening marker must be a triple-backtick fence with the lowercase
        ``json`` label on its own line. This function does not parse or validate
        the extracted JSON text.
    """
    stripped = json_str.strip()
    opening_line, separator, content = stripped.partition("\n")
    if opening_line.rstrip("\r") == "```json" and separator and content.endswith("```"):
        return content[: -len("```")].strip()
    return json_str
