"""NumeroLogic — {digits:value} notation to prevent tokenizer fragmentation.

Based on NumeroLogic (EMNLP 2024).
Example: 12345 → {5:12345}, 0.05 → {2:0.05}
"""

import re


def to_numerologic(value: float | int) -> str:
    """Convert a number to NumeroLogic format.

    Args:
        value: Number to convert.

    Returns:
        NumeroLogic string {digits:value}.

    Examples:
        >>> to_numerologic(12345)
        '{5:12345}'
        >>> to_numerologic(0.05)
        '{4:0.05}'
    """
    str_val = str(value)
    # Count significant digits (excluding decimal point and leading zeros after decimal)
    digits = len(str_val.replace(".", "").replace("-", "").lstrip("0")) or 1
    return f"{{{digits}:{value}}}"


def from_numerologic(text: str) -> float:
    """Extract number from NumeroLogic format.

    Args:
        text: NumeroLogic string like '{5:12345}'.

    Returns:
        The numeric value.
    """
    match = re.match(r"\{(\d+):(.+)\}", text.strip())
    if not match:
        raise ValueError(f"Invalid NumeroLogic format: {text}")
    return float(match.group(2))
