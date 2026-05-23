def normalize_json_str(json_str: str) -> str:
    """Strip markdown code fences from a JSON string."""
    if json_str.startswith("```json"):
        json_str = json_str[len("```json") :].strip()
    if json_str.endswith("```"):
        json_str = json_str[: -len("```")].strip()
    return json_str
