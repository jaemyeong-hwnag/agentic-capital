"""CLI for validating the local finance LLM runtime before paper trading."""

from __future__ import annotations

import json
import sys

from agentic_capital.adapters.llm.local_finance_runtime import (
    LocalFinanceRuntimeError,
    validate_local_finance_runtime,
)


def main() -> int:
    """Run health and smoke checks without printing secrets."""
    try:
        result = validate_local_finance_runtime()
    except LocalFinanceRuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
