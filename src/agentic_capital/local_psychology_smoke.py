"""CLI for validating the local psychology sidecar before agent cycles."""

from __future__ import annotations

import json
import sys

from agentic_capital.adapters.llm.local_psychology_runtime import (
    LocalPsychologyRuntimeError,
    validate_local_psychology_runtime,
)


def main() -> int:
    """Run health and smoke checks without printing secrets."""
    try:
        result = validate_local_psychology_runtime()
    except LocalPsychologyRuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
