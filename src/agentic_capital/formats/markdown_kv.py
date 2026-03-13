"""Markdown-KV format — key: value notation for LLM prompts.

Highest LLM accuracy (60.7%) for structured single records.
"""


def to_markdown_kv(data: dict[str, object]) -> str:
    """Convert a dict to Markdown-KV format.

    Args:
        data: Key-value pairs.

    Returns:
        Markdown-KV formatted string.

    Example:
        >>> to_markdown_kv({"ticker": "AAPL", "signal": "BUY", "confidence": 0.72})
        'ticker: AAPL\\nsignal: BUY\\nconfidence: 0.72'
    """
    return "\n".join(f"{k}: {v}" for k, v in data.items())


def from_markdown_kv(text: str) -> dict[str, str]:
    """Parse Markdown-KV format back to a dict.

    Args:
        text: Markdown-KV formatted string.

    Returns:
        Dict of string key-value pairs.
    """
    result: dict[str, str] = {}
    for line in text.strip().split("\n"):
        if ": " in line:
            key, value = line.split(": ", 1)
            result[key.strip()] = value.strip()
    return result
