"""Unit tests for AI-created dynamic tools (create_tool + _build_dynamic_tool)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_capital.core.tools.data_query import _build_dynamic_tool, build_agent_tools


# ---------------------------------------------------------------------------
# _build_dynamic_tool
# ---------------------------------------------------------------------------

class TestBuildDynamicTool:

    def test_valid_tool_builds_successfully(self):
        spec = {
            "name": "hello_tool",
            "description": "Returns a greeting",
            "code": "async def hello_tool(name: str = 'world') -> str:\n    return f'hello:{name}'",
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        assert tool is not None
        assert tool.name == "hello_tool"

    def test_forbidden_token_returns_none(self):
        spec = {
            "name": "bad_tool",
            "description": "Evil",
            "code": "import os\nasync def bad_tool() -> str:\n    return os.getcwd()",
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        assert tool is None

    def test_syntax_error_returns_none(self):
        spec = {
            "name": "broken_tool",
            "description": "Broken",
            "code": "async def broken_tool( -> str:\n    return 'oops'",
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        assert tool is None

    def test_function_name_mismatch_returns_none(self):
        spec = {
            "name": "expected_name",
            "description": "Mismatch",
            "code": "async def wrong_name() -> str:\n    return 'hi'",
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        assert tool is None

    @pytest.mark.asyncio
    async def test_dynamic_tool_executes(self):
        spec = {
            "name": "add_numbers",
            "description": "Adds two numbers",
            "code": "async def add_numbers(a: int, b: int = 1) -> str:\n    return f'result:{a+b}'",
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        assert tool is not None
        result = await tool.coroutine(a=3, b=4)
        assert result == "result:7"

    @pytest.mark.asyncio
    async def test_dynamic_tool_uses_trading_scope(self):
        trading = MagicMock()
        trading.get_balance = AsyncMock(
            return_value=MagicMock(total=5_000_000, available=3_000_000, currency="KRW")
        )
        spec = {
            "name": "check_cash",
            "description": "Returns available cash",
            "code": (
                "async def check_cash() -> str:\n"
                "    b = await trading.get_balance()\n"
                "    return f'avl:{b.available}'"
            ),
        }
        tool = _build_dynamic_tool(spec, trading=trading, market_data=None, recorder=None)
        assert tool is not None
        result = await tool.coroutine()
        assert "avl:3000000" in result

    @pytest.mark.asyncio
    async def test_dynamic_tool_uses_math_scope(self):
        spec = {
            "name": "calc_sqrt",
            "description": "Square root",
            "code": "async def calc_sqrt(n: float) -> str:\n    return f'sqrt:{math.sqrt(n):.2f}'",
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        result = await tool.coroutine(n=9.0)
        assert "sqrt:3.00" in result


# ---------------------------------------------------------------------------
# create_tool via build_agent_tools
# ---------------------------------------------------------------------------

class TestCreateToolTool:

    def test_create_tool_in_tool_list(self):
        tools, _, _, _ = build_agent_tools()
        names = {t.name for t in tools}
        assert "create_tool" in names

    @pytest.mark.asyncio
    async def test_create_tool_saves_to_recorder(self):
        recorder = MagicMock()
        recorder.save_tool = AsyncMock()

        tools, _, _, _ = build_agent_tools(recorder=recorder, agent_id="00000000-0000-0000-0000-000000000001")
        tool = next(t for t in tools if t.name == "create_tool")

        result = await tool.coroutine(
            name="my_metric",
            description="Custom metric",
            code="async def my_metric(x: int = 0) -> str:\n    return f'metric:{x}'",
        )
        assert result.startswith("OK:tool_created:my_metric")
        recorder.save_tool.assert_called_once()
        call_kwargs = recorder.save_tool.call_args
        assert call_kwargs[0][0] == "my_metric"  # name

    @pytest.mark.asyncio
    async def test_create_tool_rejects_forbidden_token(self):
        tools, _, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "create_tool")
        result = await tool.coroutine(
            name="bad",
            description="bad",
            code="import os\nasync def bad() -> str:\n    return os.getcwd()",
        )
        assert result.startswith("ERR:forbidden_token")

    @pytest.mark.asyncio
    async def test_create_tool_rejects_syntax_error(self):
        tools, _, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "create_tool")
        result = await tool.coroutine(
            name="broken",
            description="bad",
            code="async def broken( -> str:\n    pass",
        )
        assert result.startswith("ERR:syntax")

    @pytest.mark.asyncio
    async def test_create_tool_rejects_missing_function(self):
        tools, _, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "create_tool")
        result = await tool.coroutine(
            name="expected",
            description="bad",
            code="async def different_name() -> str:\n    return 'hi'",
        )
        assert result.startswith("ERR:fn_not_found")

    @pytest.mark.asyncio
    async def test_create_tool_no_recorder_still_validates(self):
        """Even without recorder, validation runs and reports success (no persistence)."""
        tools, _, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "create_tool")
        result = await tool.coroutine(
            name="valid_tool",
            description="A valid tool",
            code="async def valid_tool(n: int = 1) -> str:\n    return f'ok:{n}'",
        )
        assert result.startswith("OK:tool_created:valid_tool")


# ---------------------------------------------------------------------------
# preloaded_tools injection
# ---------------------------------------------------------------------------

class TestPreloadedTools:

    def test_preloaded_tools_added_to_list(self):
        from langchain_core.tools import StructuredTool

        async def my_fn() -> str:
            return "hi"

        extra = StructuredTool.from_function(coroutine=my_fn, name="my_fn", description="test")
        tools, _, _, _ = build_agent_tools(preloaded_tools=[extra])
        names = {t.name for t in tools}
        assert "my_fn" in names

    def test_none_preloaded_tools_skipped(self):
        tools, _, _, _ = build_agent_tools(preloaded_tools=[None, None])
        # Should not crash, just skip None entries
        assert isinstance(tools, list)


class TestDynamicToolSafeExecution:
    """Dynamic tool runtime errors must not propagate — must return ERR: string."""

    @pytest.mark.asyncio
    async def test_runtime_error_returns_err_string(self):
        """Tool that raises at runtime should return ERR: not propagate exception."""
        spec = {
            "name": "fail_tool",
            "description": "Always fails at runtime",
            "code": (
                "async def fail_tool(x: int = 1) -> str:\n"
                "    raise ValueError('intentional failure')\n"
                "    return 'never'"
            ),
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        assert tool is not None
        result = await tool.coroutine(x=1)
        assert result.startswith("ERR:tool_exec:")
        assert "fail_tool" in result
        assert "intentional failure" in result

    @pytest.mark.asyncio
    async def test_runtime_error_does_not_raise(self):
        """Calling a failing dynamic tool must not raise any exception to caller."""
        spec = {
            "name": "crash_tool",
            "description": "Crashes",
            "code": "async def crash_tool() -> str:\n    raise RuntimeError('boom')",
        }
        tool = _build_dynamic_tool(spec, trading=None, market_data=None, recorder=None)
        # This must not raise — previously would propagate through LangGraph
        result = await tool.coroutine()
        assert isinstance(result, str)
        assert "ERR:" in result
