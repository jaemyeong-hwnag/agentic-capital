"""Unit tests for build_agent_tools() and KIS WebSocket adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.core.tools.data_query import build_agent_tools


def _make_trading():
    trading = MagicMock()
    trading.get_balance = AsyncMock(
        return_value=MagicMock(total=10_000_000, available=8_000_000, currency="KRW")
    )
    trading.get_positions = AsyncMock(return_value=[
        MagicMock(
            symbol="005930", quantity=100, avg_price=70000,
            current_price=72000, unrealized_pnl=200000, unrealized_pnl_pct=2.86,
            market="kr_stock", currency="KRW",
        ),
    ])
    trading.submit_order = AsyncMock(
        return_value=MagicMock(
            order_id="ORDER123", symbol="005930", side="buy",
            quantity=10, filled_price=70000.0, status="submitted", market="kr_stock",
        )
    )
    trading.cancel_order = AsyncMock(return_value=True)
    trading.get_fills = AsyncMock(return_value=[
        MagicMock(order_id="O1", symbol="005930", side="buy", quantity=10, filled_price=70000, status="filled"),
    ])
    return trading


def _make_market_data():
    md = MagicMock()
    md.get_quote = AsyncMock(
        return_value=MagicMock(
            symbol="005930", price=72000, bid=71900, ask=72100, volume=5_000_000,
            market="kr_stock", currency="KRW",
        )
    )
    md.get_ohlcv = AsyncMock(return_value=[
        MagicMock(timestamp="2026-01-01", open=70000, high=73000, low=69000, close=72000, volume=3_000_000),
    ])
    md.get_symbols = AsyncMock(return_value=["005930", "000660"])
    md.get_order_book = AsyncMock(
        return_value=MagicMock(
            symbol="005930",
            bids=[MagicMock(price=71900, quantity=100)],
            asks=[MagicMock(price=72100, quantity=200)],
            timestamp="2026-01-01",
        )
    )
    md.get_fills = AsyncMock(return_value=[])
    return md


class TestBuildAgentTools:
    """Test build_agent_tools() returns correct tools and they work."""

    def test_returns_tools_and_sinks(self):
        tools, decisions, messages = build_agent_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert isinstance(decisions, list)
        assert isinstance(messages, list)

    def test_tool_names(self):
        tools, _, _ = build_agent_tools()
        names = {t.name for t in tools}
        assert "get_balance" in names
        assert "get_positions" in names
        assert "get_quote" in names
        assert "get_ohlcv" in names
        assert "get_order_book" in names
        assert "get_symbols" in names
        assert "get_fills" in names
        assert "submit_order" in names
        assert "cancel_order" in names
        assert "save_memory" in names
        assert "search_memory" in names
        assert "send_message" in names

    @pytest.mark.asyncio
    async def test_get_balance_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert result["total"] == 10_000_000
        assert result["currency"] == "KRW"

    @pytest.mark.asyncio
    async def test_get_balance_no_trading(self):
        tools, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_positions_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_positions")
        result = await tool.coroutine()
        assert len(result) == 1
        assert result[0]["symbol"] == "005930"

    @pytest.mark.asyncio
    async def test_get_quote_tool(self):
        md = _make_market_data()
        tools, _, _ = build_agent_tools(market_data=md)
        tool = next(t for t in tools if t.name == "get_quote")
        result = await tool.coroutine(symbol="005930")
        assert result["price"] == 72000
        assert result["symbol"] == "005930"

    @pytest.mark.asyncio
    async def test_get_ohlcv_tool(self):
        md = _make_market_data()
        tools, _, _ = build_agent_tools(market_data=md)
        tool = next(t for t in tools if t.name == "get_ohlcv")
        result = await tool.coroutine(symbol="005930", timeframe="1d", limit=10)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_order_book_tool(self):
        md = _make_market_data()
        tools, _, _ = build_agent_tools(market_data=md)
        tool = next(t for t in tools if t.name == "get_order_book")
        result = await tool.coroutine(symbol="005930")
        assert "bids" in result
        assert "asks" in result

    @pytest.mark.asyncio
    async def test_get_symbols_tool(self):
        md = _make_market_data()
        tools, _, _ = build_agent_tools(market_data=md)
        tool = next(t for t in tools if t.name == "get_symbols")
        result = await tool.coroutine(market="kr_stock")
        assert "005930" in result

    @pytest.mark.asyncio
    async def test_get_fills_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_fills")
        result = await tool.coroutine()
        assert len(result) == 1
        assert result[0]["order_id"] == "O1"

    @pytest.mark.asyncio
    async def test_submit_order_tool_records_decision(self):
        trading = _make_trading()
        tools, decisions, _ = build_agent_tools(trading=trading, agent_name="Trader-1")
        tool = next(t for t in tools if t.name == "submit_order")
        result = await tool.coroutine(
            symbol="005930", side="buy", quantity=10, price=70000.0
        )
        assert result["status"] == "submitted"
        assert len(decisions) == 1
        assert decisions[0]["symbol"] == "005930"
        assert decisions[0]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_submit_order_no_trading(self):
        tools, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "submit_order")
        result = await tool.coroutine(symbol="005930", side="buy", quantity=10)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_cancel_order_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "cancel_order")
        result = await tool.coroutine(order_id="ORDER123")
        assert result["cancelled"] is True

    @pytest.mark.asyncio
    async def test_save_and_search_memory(self):
        memory = {}
        tools, _, _ = build_agent_tools(agent_memory=memory)

        save_tool = next(t for t in tools if t.name == "save_memory")
        search_tool = next(t for t in tools if t.name == "search_memory")

        await save_tool.coroutine(content="Samsung Electronics up 5%", keywords=["005930", "bullish"])
        results = await search_tool.coroutine(query="bullish")
        assert len(results) == 1
        assert "Samsung" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_search_memory_no_match(self):
        memory = {}
        tools, _, _ = build_agent_tools(agent_memory=memory)
        search_tool = next(t for t in tools if t.name == "search_memory")
        results = await search_tool.coroutine(query="nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_send_message_tool(self):
        tools, _, messages = build_agent_tools(agent_name="CEO-Alpha")
        tool = next(t for t in tools if t.name == "send_message")
        result = await tool.coroutine(
            to_agent="Trader-Gamma",
            type="INSTRUCTION",
            content={"action": "buy", "symbol": "005930"},
        )
        assert result["sent"] is True
        assert len(messages) == 1
        assert messages[0]["to"] == "Trader-Gamma"
        assert messages[0]["from"] == "CEO-Alpha"


class TestKISWebSocket:
    """Test KISWebSocketAdapter."""

    def _make_session(self, is_paper=True):
        from unittest.mock import patch
        from agentic_capital.adapters.kis_session import KISSession
        with patch("agentic_capital.adapters.kis_session.settings") as mock_s:
            mock_s.kis_app_key = "test-key"
            mock_s.kis_app_secret = "test-secret"
            mock_s.kis_account_no = "5017463701"
            mock_s.kis_is_paper = is_paper
            return KISSession()

    def test_paper_url(self):
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        assert ":31000" in ws._ws_url

    def test_real_url(self):
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=False)
        ws = KISWebSocketAdapter(session=session)
        assert ":21000" in ws._ws_url

    @pytest.mark.asyncio
    async def test_subscribe_overseas_paper_raises(self):
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._approval_key = "test-key"
        ws._ws = MagicMock()
        ws._ws.send = AsyncMock()

        with pytest.raises(NotImplementedError, match="paper"):
            await ws.subscribe_overseas_price("AAPL", "NASD", callback=AsyncMock())

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_domestic_price(self):
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._approval_key = "test-key"
        ws._ws = MagicMock()
        ws._ws.send = AsyncMock()

        cb = AsyncMock()
        await ws.subscribe_price("005930", callback=cb)
        assert len(ws._callbacks) == 1

        await ws.unsubscribe_price("005930")
        assert len(ws._callbacks) == 0

    @pytest.mark.asyncio
    async def test_subscribe_order_book(self):
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._approval_key = "test-key"
        ws._ws = MagicMock()
        ws._ws.send = AsyncMock()

        cb = AsyncMock()
        await ws.subscribe_order_book("005930", callback=cb)
        assert any("H0STASP0" in k for k in ws._callbacks)

    @pytest.mark.asyncio
    async def test_disconnect_no_ws(self):
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        # Should not raise
        await ws.disconnect()

    def test_parse_tick_domestic_price(self):
        from agentic_capital.adapters.kis_websocket import _parse_tick, _TR_DOMESTIC_PRICE
        # Simulate a domestic price tick with enough fields
        fields = ["005930", "091500", "72000", "500", "1000", "0", "0", "0", "0", "5000000"] + [""] * 10
        body = "^".join(fields)
        tick = _parse_tick(_TR_DOMESTIC_PRICE, body)
        assert tick is not None
        assert tick["symbol"] == "005930"
        assert tick["price"] == 72000.0
        assert tick["type"] == "trade"

    def test_parse_tick_unknown_tr(self):
        from agentic_capital.adapters.kis_websocket import _parse_tick
        tick = _parse_tick("UNKNOWN_TR", "field1^field2")
        assert tick is None

    def test_parse_tick_too_short(self):
        from agentic_capital.adapters.kis_websocket import _parse_tick, _TR_DOMESTIC_PRICE
        tick = _parse_tick(_TR_DOMESTIC_PRICE, "only^3^fields")
        assert tick is None


class TestKISWebSocketExtended:
    """Extended WebSocket tests for message handling."""

    def _make_session(self, is_paper=True):
        with patch("agentic_capital.adapters.kis_session.settings") as mock_s:
            from agentic_capital.adapters.kis_session import KISSession
            mock_s.kis_app_key = "test-key"
            mock_s.kis_app_secret = "test-secret"
            mock_s.kis_account_no = "5017463701"
            mock_s.kis_is_paper = is_paper
            return KISSession()

    @pytest.mark.asyncio
    async def test_handle_message_pingpong(self):
        """WebSocket ping-pong messages trigger pong response."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._ws = MagicMock()
        ws._ws.send = AsyncMock()

        # Simulate PINGPONG message
        pingpong = '{"header": {"tr_id": "PINGPONG"}}'
        await ws._handle_message(pingpong)
        ws._ws.send.assert_called_once_with(pingpong)

    @pytest.mark.asyncio
    async def test_handle_message_trade_tick_dispatches_callback(self):
        """Trade tick dispatches to registered callback."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter, _TR_DOMESTIC_PRICE
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._ws = MagicMock()

        received = []

        async def cb(tick):
            received.append(tick)

        # Register callback
        tr_key = f"{_TR_DOMESTIC_PRICE}|005930"
        ws._callbacks[tr_key] = cb

        # Build a fake domestic price message with enough fields
        fields = ["005930", "091500", "72000", "500", "1000", "0", "0", "0", "0", "5000000"] + [""] * 10
        body = "^".join(fields)
        raw = f"0|{_TR_DOMESTIC_PRICE}|1|{body}"
        await ws._handle_message(raw)

        assert len(received) == 1
        assert received[0]["price"] == 72000.0

    @pytest.mark.asyncio
    async def test_handle_message_bytes_decoded(self):
        """Bytes messages are decoded and processed."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._ws = MagicMock()

        # Bytes that decode to a JSON control message
        msg = '{"header": {"tr_id": "CONNECTED"}}'
        await ws._handle_message(msg.encode("utf-8"))
        # Should not raise

    @pytest.mark.asyncio
    async def test_handle_message_malformed_no_crash(self):
        """Malformed messages do not crash the handler."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._ws = MagicMock()

        await ws._handle_message("not|valid|enough")
        # Should not raise

    def test_parse_tick_domestic_ask(self):
        """Order book tick returns bid/ask prices."""
        from agentic_capital.adapters.kis_websocket import _parse_tick, _TR_DOMESTIC_ASK
        fields = ["005930", "091500", "", "72100"] + [""] * 9 + ["71900"] + [""] * 5
        body = "^".join(fields)
        tick = _parse_tick(_TR_DOMESTIC_ASK, body)
        assert tick is not None
        assert tick["type"] == "orderbook"
        assert tick["ask1_price"] == 72100.0
        assert tick["bid1_price"] == 71900.0

    def test_parse_tick_overseas(self):
        """Overseas price tick returns correct fields."""
        from agentic_capital.adapters.kis_websocket import _parse_tick, _TR_OVERSEAS_PRICE
        fields = ["AAPL", "NASD", "185.50", "0", "0", "0", "5000000"]
        body = "^".join(fields)
        tick = _parse_tick(_TR_OVERSEAS_PRICE, body)
        assert tick is not None
        assert tick["price"] == 185.5
        assert tick["volume"] == 5000000.0

    @pytest.mark.asyncio
    async def test_send_subscribe_no_ws_raises(self):
        """_send_subscribe raises if not connected."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._approval_key = "test-key"
        ws._ws = None

        with pytest.raises(RuntimeError, match="not connected"):
            await ws._send_subscribe("H0STCNT0", "005930")

    @pytest.mark.asyncio
    async def test_unsubscribe_order_book(self):
        """unsubscribe_order_book removes callback and sends unsubscribe."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._approval_key = "test-key"
        ws._ws = MagicMock()
        ws._ws.send = AsyncMock()

        cb = AsyncMock()
        await ws.subscribe_order_book("005930", callback=cb)
        assert len(ws._callbacks) == 1

        await ws.unsubscribe_order_book("005930")
        assert len(ws._callbacks) == 0


class TestKISWebSocketConnect:
    """Tests for WebSocket connect/disconnect lifecycle."""

    def _make_session(self, is_paper=True):
        with patch("agentic_capital.adapters.kis_session.settings") as mock_s:
            from agentic_capital.adapters.kis_session import KISSession
            mock_s.kis_app_key = "test-key"
            mock_s.kis_app_secret = "test-secret"
            mock_s.kis_account_no = "5017463701"
            mock_s.kis_is_paper = is_paper
            return KISSession()

    @pytest.mark.asyncio
    async def test_connect_sets_connected(self):
        """connect() sets _connected=True and starts listen task."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)

        mock_ws_conn = MagicMock()
        mock_ws_conn.__aiter__ = MagicMock(return_value=iter([]))

        async def noop_listen():
            pass

        with patch("agentic_capital.adapters.kis_websocket.KISWebSocketAdapter._get_approval_key",
                   new_callable=AsyncMock, return_value="test-approval-key"), \
             patch("websockets.connect", new_callable=AsyncMock, return_value=mock_ws_conn):
            await ws.connect()

        assert ws._connected is True
        assert ws._approval_key == "test-approval-key"
        # Cleanup
        ws._connected = False
        if ws._listen_task:
            ws._listen_task.cancel()

    @pytest.mark.asyncio
    async def test_disconnect_with_task(self):
        """disconnect() cancels listen task and closes websocket."""
        import asyncio
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._connected = True

        # Create a real task that will be cancelled
        async def forever():
            await asyncio.sleep(1000)

        ws._listen_task = asyncio.create_task(forever())
        ws._ws = MagicMock()
        ws._ws.close = AsyncMock()

        await ws.disconnect()
        assert ws._connected is False

    @pytest.mark.asyncio
    async def test_send_subscribe_sends_json(self):
        """_send_subscribe sends correct JSON to websocket."""
        import json
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._approval_key = "test-key"
        ws._ws = MagicMock()
        ws._ws.send = AsyncMock()

        await ws._send_subscribe("H0STCNT0", "005930")

        ws._ws.send.assert_called_once()
        sent = json.loads(ws._ws.send.call_args[0][0])
        assert sent["header"]["tr_type"] == "1"
        assert sent["body"]["input"]["tr_id"] == "H0STCNT0"

    @pytest.mark.asyncio
    async def test_send_unsubscribe_sends_json(self):
        """_send_unsubscribe sends correct JSON with tr_type=2."""
        import json
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._approval_key = "test-key"
        ws._ws = MagicMock()
        ws._ws.send = AsyncMock()

        await ws._send_unsubscribe("H0STCNT0", "005930")

        ws._ws.send.assert_called_once()
        sent = json.loads(ws._ws.send.call_args[0][0])
        assert sent["header"]["tr_type"] == "2"

    @pytest.mark.asyncio
    async def test_listen_loop_exits_on_disconnect(self):
        """_listen_loop exits cleanly when _connected is False."""
        from agentic_capital.adapters.kis_websocket import KISWebSocketAdapter
        session = self._make_session(is_paper=True)
        ws = KISWebSocketAdapter(session=session)
        ws._connected = False
        ws._ws = None
        # Should exit immediately
        await ws._listen_loop()
