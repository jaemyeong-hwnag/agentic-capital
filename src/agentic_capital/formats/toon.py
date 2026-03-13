"""TOON format — Token-Oriented Object Notation for LLM prompts.

40-60% token reduction vs JSON for tabular data.
Format: @name[count](columns)\\nrow1\\nrow2\\n...
"""

import structlog

logger = structlog.get_logger()


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

    Raises:
        ValueError: If the TOON string is malformed.
    """
    try:
        lines = toon_str.strip().split("\n")
        header = lines[0]

        # Parse @name[count](col1,col2,...)
        at_idx = header.find("@")
        bracket_open = header.find("[")
        paren_open = header.find("(")
        paren_close = header.find(")")

        if any(idx == -1 for idx in (at_idx, bracket_open, paren_open, paren_close)):
            raise ValueError(f"Malformed TOON header: {header}")

        name = header[at_idx + 1 : bracket_open]
        columns = header[paren_open + 1 : paren_close].split(",")

        rows = [line.split(",") for line in lines[1:] if line.strip()]
        return name, columns, rows
    except ValueError:
        raise
    except Exception:
        logger.exception("toon_parse_failed", input_len=len(toon_str))
        raise ValueError(f"Failed to parse TOON string: {toon_str[:100]}")
