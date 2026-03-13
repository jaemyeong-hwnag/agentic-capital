"""Tests for main entrypoint."""

import pytest

from agentic_capital.main import main, run


class TestMain:
    @pytest.mark.asyncio
    async def test_run(self) -> None:
        await run()

    def test_main_exists(self) -> None:
        assert callable(main)
