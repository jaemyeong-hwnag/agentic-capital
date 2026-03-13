"""Tests for main entrypoint."""

from unittest.mock import patch

import pytest

from agentic_capital.main import main, run, run_migrations


class TestMain:
    @pytest.mark.asyncio
    async def test_run(self) -> None:
        with patch("agentic_capital.main.run_migrations"):
            await run()

    def test_main_exists(self) -> None:
        assert callable(main)

    def test_run_migrations_callable(self) -> None:
        assert callable(run_migrations)
