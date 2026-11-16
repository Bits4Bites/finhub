def normalize_json_str(json_str: str) -> str:
    """Extract JSON text from an optional Markdown JSON code block.

    Args:
        json_str: JSON text, optionally wrapped in a complete Markdown code block
            with the lowercase ``json`` language label.

    Returns:
        The JSON text without its code-block markers or surrounding whitespace.
        Text without one complete supported code block is returned unchanged,
        including its original whitespace.

    Notes:
        The opening line must contain exactly three backticks followed by the
        lowercase label ``json``. The closing line must contain exactly three
        backticks. Both fences must be on their own lines, and only surrounding
        whitespace may appear outside them. Unix and Windows line endings are
        supported. This function does not parse or validate the extracted JSON
        text.
    """
    stripped = json_str.strip()
    lines = stripped.splitlines(keepends=True)
    if len(lines) < 2:
        return json_str
    if lines[0].rstrip("\r\n") != "```json" or lines[-1] != "```":
        return json_str
    if any(line.rstrip("\r\n") == "```" for line in lines[1:-1]):
        return json_str
    return "".join(lines[1:-1]).strip()
