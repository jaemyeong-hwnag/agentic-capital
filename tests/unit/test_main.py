"""Tests for main entrypoint."""

from unittest.mock import AsyncMock, patch

import pytest

from agentic_capital.main import main, run_migrations


class TestMain:
    def test_main_exists(self) -> None:
        assert callable(main)

    def test_run_migrations_callable(self) -> None:
        assert callable(run_migrations)
