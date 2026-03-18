"""Tests for main entrypoints."""

import sys
from unittest.mock import AsyncMock, patch

import pytest

from agentic_capital.main import main
from agentic_capital.futures import main as futures_main


class TestMain:
    def test_main_exists(self) -> None:
        assert callable(main)

    def test_futures_main_exists(self) -> None:
        assert callable(futures_main)

    def test_main_keyboard_interrupt(self) -> None:
        with patch("agentic_capital.main.asyncio.run", side_effect=KeyboardInterrupt), \
             pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

    def test_main_exception(self) -> None:
        with patch("agentic_capital.main.asyncio.run", side_effect=RuntimeError("crash")), \
             pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_futures_main_keyboard_interrupt(self) -> None:
        with patch("agentic_capital.futures.asyncio.run", side_effect=KeyboardInterrupt), \
             pytest.raises(SystemExit) as exc:
            futures_main()
        assert exc.value.code == 0

    def test_futures_main_exception(self) -> None:
        with patch("agentic_capital.futures.asyncio.run", side_effect=RuntimeError("crash")), \
             pytest.raises(SystemExit) as exc:
            futures_main()
        assert exc.value.code == 1
