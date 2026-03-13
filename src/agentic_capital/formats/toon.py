"""TOON format — Token-Oriented Object Notation for LLM prompts.

40-60% token reduction vs JSON for tabular data.
Format: @name[count](columns)\\nrow1\\nrow2\\n...
"""


def to_toon(name: str, columns: list[str], rows: list[list[str]]) -> str:
    """Convert tabular data to TOON format.

    Args:
        name: Table name.
        columns: Column headers.
        rows: Data rows (each row is a list of string values).

    Returns:
        TOON-formatted string.

    Example:
        >>> to_toon("prices", ["ticker", "close", "vol"], [["AAPL", "+0.8", "1.1x"]])
        '@prices[1](ticker,close,vol)\\nAAPL,+0.8,1.1x'
    """
    header = f"@{name}[{len(rows)}]({','.join(columns)})"
    body = "\n".join(",".join(row) for row in rows)
    return f"{header}\n{body}"


def from_toon(toon_str: str) -> tuple[str, list[str], list[list[str]]]:
    """Parse TOON format back to structured data.

    Returns:
        Tuple of (name, columns, rows).
    """
    lines = toon_str.strip().split("\n")
    header = lines[0]

    # Parse @name[count](col1,col2,...)
    at_idx = header.index("@")
    bracket_open = header.index("[")
    paren_open = header.index("(")
    paren_close = header.index(")")

    name = header[at_idx + 1 : bracket_open]
    columns = header[paren_open + 1 : paren_close].split(",")

    rows = [line.split(",") for line in lines[1:] if line.strip()]
    return name, columns, rows
