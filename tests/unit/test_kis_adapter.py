"""Unit tests for KIS trading and market data adapters."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.adapters.kis_session import KISSession
from agentic_capital.adapters.trading.kis import KISTradingAdapter
from agentic_capital.adapters.market_data.kis import KISMarketDataAdapter
from agentic_capital.ports.trading import Order, OrderSide, OrderType


def _make_session(*, is_paper: bool = True) -> KISSession:
    """Create a KISSession with mocked settings."""
    with patch("agentic_capital.adapters.kis_session.settings") as mock_s:
        mock_s.kis_app_key = "test-key"
        mock_s.kis_app_secret = "test-secret"
        mock_s.kis_account_no = "5017463701"
        mock_s.kis_is_paper = is_paper
        return KISSession()


class TestKISSession:
    """Test KISSession token management."""

    def test_paper_mode(self):
        session = _make_session(is_paper=True)
        assert "openapivts" in session.base_url
        assert session.cano == "50174637"
        assert session.prdt_cd == "01"

    def test_live_mode(self):
        session = _make_session(is_paper=False)
        assert "openapi.koreainvestment" in session.base_url

    @pytest.mark.asyncio
    async def test_ensure_token(self):
        session = _make_session()
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "test-token-123"}
        session.client = MagicMock()
        session.client.post = AsyncMock(return_value=mock_response)

        token = await session.ensure_token()
        assert token == "test-token-123"

    @pytest.mark.asyncio
    async def test_ensure_token_cached(self):
        session = _make_session()
        session._access_token = "cached-token"
        token = await session.ensure_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_ensure_token_failure(self):
        session = _make_session()
        mock_response = MagicMock()
        mock_response.json.return_value = {"error_code": "EGW00000", "error_description": "invalid credentials"}
        session.client = MagicMock()
        session.client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="KIS token failed"):
            await session.ensure_token()

    def test_headers(self):
        session = _make_session()
        session._access_token = "test-token"
        headers = session.headers("VTTC8434R")
        assert headers["authorization"] == "Bearer test-token"
        assert headers["tr_id"] == "VTTC8434R"
        assert headers["appkey"] == "test-key"


class TestKISTradingAdapter:
    """Test KISTradingAdapter."""

    def _make_adapter(self, *, is_paper: bool = True) -> KISTradingAdapter:
        session = _make_session(is_paper=is_paper)
        session._access_token = "token"
        return KISTradingAdapter(session=session)

    def test_init_requires_credentials(self):
        with patch("agentic_capital.adapters.kis_session.settings") as mock_s:
            mock_s.kis_app_key = ""
            mock_s.kis_app_secret = ""
            mock_s.kis_account_no = ""
            mock_s.kis_is_paper = True
            with pytest.raises(ValueError, match="KIS_APP_KEY"):
                KISSession()

    def test_tr_id_paper(self):
        adapter = self._make_adapter(is_paper=True)
        assert adapter._tr_id("balance") == "VTTC8434R"
        assert adapter._tr_id("order_buy") == "VTTC0802U"

    def test_tr_id_live(self):
        adapter = self._make_adapter(is_paper=False)
        assert adapter._tr_id("balance") == "TTTC8434R"
        assert adapter._tr_id("order_sell") == "TTTC0801U"

    @pytest.mark.asyncio
    async def test_get_balance(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output2": [{"tot_evlu_amt": "10000000", "dnca_tot_amt": "5000000"}],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)

        balance = await adapter.get_balance()
        assert balance.total == 10_000_000.0
        assert balance.available == 5_000_000.0
        assert balance.currency == "KRW"

    @pytest.mark.asyncio
    async def test_get_balance_error(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "2", "msg1": "INVALID"}
        adapter._session.get = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="KIS balance failed"):
            await adapter.get_balance()

    @pytest.mark.asyncio
    async def test_get_positions_empty(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "0", "output1": []}
        adapter._session.get = AsyncMock(return_value=mock_response)

        positions = await adapter.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_with_data(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output1": [{
                "pdno": "005930",
                "hldg_qty": "10",
                "pchs_avg_pric": "70000",
                "prpr": "72000",
                "evlu_pfls_amt": "20000",
                "evlu_pfls_rt": "2.86",
            }],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)

        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "005930"
        assert positions[0].quantity == 10.0

    @pytest.mark.asyncio
    async def test_submit_order_success(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": {"ODNO": "ORDER123"},
        }
        adapter._session.post = AsyncMock(return_value=mock_response)

        order = Order(symbol="005930", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=70000)
        result = await adapter.submit_order(order)
        assert result.order_id == "ORDER123"
        assert result.status == "submitted"

    @pytest.mark.asyncio
    async def test_submit_order_rejected(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "2", "msg1": "잔고 부족"}
        adapter._session.post = AsyncMock(return_value=mock_response)

        order = Order(symbol="005930", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
        result = await adapter.submit_order(order)
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_get_order_status(self):
        adapter = self._make_adapter()
        result = await adapter.get_order_status("ORDER123")
        assert result.order_id == "ORDER123"
        assert result.status == "unknown"

    @pytest.mark.asyncio
    async def test_get_quote(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "72000",
                "prdy_vrss": "1000",
                "prdy_ctrt": "1.41",
                "acml_vol": "5000000",
            },
        }
        adapter._session.get = AsyncMock(return_value=mock_response)

        quote = await adapter.get_quote("005930")
        assert quote["price"] == 72000
        assert quote["change"] == 1000

    @pytest.mark.asyncio
    async def test_submit_overseas_order_paper_raises(self):
        """Overseas orders must raise NotImplementedError in paper mode."""
        from agentic_capital.ports.trading import Market
        adapter = self._make_adapter(is_paper=True)
        order = Order(
            symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=5, price=185.0, market=Market.US_STOCK, exchange="NASD",
        )
        with pytest.raises(NotImplementedError, match="paper"):
            await adapter.submit_order(order)

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """cancel_order sends correct TR_ID and returns True on success."""
        adapter = self._make_adapter(is_paper=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": {"ODNO": "ORDER123"},
        }
        adapter._session.post = AsyncMock(return_value=mock_response)
        success = await adapter.cancel_order("ORDER123", symbol="005930", quantity=10)
        assert success is True

    @pytest.mark.asyncio
    async def test_get_fills_empty(self):
        """get_fills returns empty list when API returns no data."""
        adapter = self._make_adapter(is_paper=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "0", "output1": []}
        adapter._session.get = AsyncMock(return_value=mock_response)
        fills = await adapter.get_fills()
        assert fills == []


class TestKISMarketDataAdapter:
    """Test KISMarketDataAdapter."""

    def _make_adapter(self, *, is_paper: bool = True) -> KISMarketDataAdapter:
        session = _make_session(is_paper=is_paper)
        session._access_token = "token"
        return KISMarketDataAdapter(session=session)

    def test_init_paper(self):
        adapter = self._make_adapter(is_paper=True)
        assert "openapivts" in adapter._session.base_url

    def test_init_live(self):
        adapter = self._make_adapter(is_paper=False)
        assert "openapi.koreainvestment" in adapter._session.base_url

    @pytest.mark.asyncio
    async def test_get_symbols_kr(self):
        adapter = self._make_adapter()
        symbols = await adapter.get_symbols()
        assert "005930" in symbols
        assert len(symbols) == 10

    @pytest.mark.asyncio
    async def test_get_symbols_us(self):
        adapter = self._make_adapter()
        symbols = await adapter.get_symbols("us_stock")
        assert "AAPL" in symbols
        assert len(symbols) == 10

    @pytest.mark.asyncio
    async def test_get_symbols_unknown_market(self):
        adapter = self._make_adapter()
        symbols = await adapter.get_symbols("unknown_market")
        assert symbols == []

    @pytest.mark.asyncio
    async def test_get_quote(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "72000",
                "bidp1": "71900",
                "askp1": "72100",
                "acml_vol": "5000000",
            },
        }
        adapter._session.get = AsyncMock(return_value=mock_response)

        quote = await adapter.get_quote("005930")
        assert quote.price == 72000.0
        assert quote.symbol == "005930"

    @pytest.mark.asyncio
    async def test_get_ohlcv(self):
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": [
                {
                    "stck_bsop_date": "20260313",
                    "stck_oprc": "71000",
                    "stck_hgpr": "73000",
                    "stck_lwpr": "70500",
                    "stck_clpr": "72000",
                    "acml_vol": "5000000",
                },
                {
                    "stck_bsop_date": "20260312",
                    "stck_oprc": "70000",
                    "stck_hgpr": "71500",
                    "stck_lwpr": "69500",
                    "stck_clpr": "71000",
                    "acml_vol": "4500000",
                },
            ],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)

        candles = await adapter.get_ohlcv("005930", limit=10)
        assert len(candles) == 2
        assert candles[0].close == 72000.0
        assert candles[1].open == 70000.0

    @pytest.mark.asyncio
    async def test_get_ohlcv_weekly(self):
        """Weekly OHLCV uses FID_PERIOD_DIV_CODE=W."""
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": [
                {
                    "stck_bsop_date": "20260313",
                    "stck_oprc": "70000",
                    "stck_hgpr": "73000",
                    "stck_lwpr": "69500",
                    "stck_clpr": "72500",
                    "acml_vol": "25000000",
                },
            ],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        candles = await adapter.get_ohlcv("005930", timeframe="1w", limit=5)
        assert len(candles) == 1
        assert candles[0].high == 73000.0

    @pytest.mark.asyncio
    async def test_get_ohlcv_minute(self):
        """Minute OHLCV uses minute endpoint."""
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output2": [
                {
                    "stck_bsop_date": "20260313",
                    "stck_cntg_hour": "091500",
                    "stck_oprc": "71000",
                    "stck_hgpr": "71500",
                    "stck_lwpr": "70800",
                    "stck_prpr": "71200",
                    "cntg_vol": "100000",
                },
            ],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        candles = await adapter.get_ohlcv("005930", timeframe="5m", limit=5)
        assert len(candles) == 1
        assert candles[0].close == 71200.0

    @pytest.mark.asyncio
    async def test_get_quote_overseas(self):
        """Overseas stock quote uses HHDFS00000300."""
        adapter = self._make_adapter(is_paper=False)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": {
                "last": "185.50",
                "bidp": "185.40",
                "askp": "185.60",
                "tvol": "50000000",
            },
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        quote = await adapter.get_quote("AAPL", market="us_stock", exchange="NASD")
        assert quote.price == 185.5
        assert quote.currency == "USD"
        assert quote.market == "us_stock"

    @pytest.mark.asyncio
    async def test_get_ohlcv_overseas(self):
        """Overseas OHLCV uses HHDFS76240000."""
        adapter = self._make_adapter(is_paper=False)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output2": [
                {
                    "xymd": "20260313",
                    "open": "183.00",
                    "high": "186.50",
                    "low": "182.50",
                    "clos": "185.50",
                    "tvol": "55000000",
                },
            ],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        candles = await adapter.get_ohlcv("AAPL", timeframe="1d", limit=5, market="us_stock", exchange="NASD")
        assert len(candles) == 1
        assert candles[0].close == 185.5

    @pytest.mark.asyncio
    async def test_get_order_book(self):
        """Domestic order book uses FHKST01010200."""
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output1": {
                "askp1": "72100", "askp_rsqn1": "500",
                "askp2": "72200", "askp_rsqn2": "300",
                "bidp1": "71900", "bidp_rsqn1": "800",
                "bidp2": "71800", "bidp_rsqn2": "600",
            },
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        book = await adapter.get_order_book("005930", depth=2)
        assert book.symbol == "005930"
        assert len(book.asks) == 2
        assert len(book.bids) == 2
        assert book.asks[0].price == 72100.0
        assert book.bids[0].price == 71900.0


class TestKISTradingAdapterExtended:
    """Extended tests for overseas/fills/cancel in KIS Trading Adapter."""

    def _make_adapter(self, *, is_paper: bool = True) -> KISTradingAdapter:
        session = _make_session(is_paper=is_paper)
        session._access_token = "token"
        return KISTradingAdapter(session=session)

    @pytest.mark.asyncio
    async def test_get_overseas_balance(self):
        """get_overseas_balance returns foreign balance (real mode only)."""
        adapter = self._make_adapter(is_paper=False)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output2": [{"tot_evlu_pfls_amt": "5000000", "frcr_evlu_amt2": "3500.00", "frcr_dncl_amt_2": "1000.00"}],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        bal = await adapter.get_overseas_balance("USD")
        assert bal.total == 3500.0
        assert bal.available == 1000.0
        assert bal.currency == "USD"

    @pytest.mark.asyncio
    async def test_get_overseas_balance_paper_raises(self):
        """get_overseas_balance raises NotImplementedError in paper mode."""
        adapter = self._make_adapter(is_paper=True)
        with pytest.raises(NotImplementedError, match="paper"):
            await adapter.get_overseas_balance()

    @pytest.mark.asyncio
    async def test_get_positions_live_fetches_overseas(self):
        """get_positions in live mode fetches domestic + overseas."""
        from agentic_capital.adapters.trading.kis import KISTradingAdapter
        adapter = self._make_adapter(is_paper=False)

        domestic_resp = MagicMock()
        domestic_resp.json.return_value = {"rt_cd": "0", "output1": []}

        overseas_resp = MagicMock()
        overseas_resp.json.return_value = {
            "rt_cd": "0",
            "output1": [{
                "ovrs_pdno": "AAPL",
                "ovrs_cblc_qty": "5",
                "pchs_avg_pric": "180.00",
                "now_pric2": "185.50",
                "frcr_evlu_pfls_amt": "27.50",
                "evlu_pfls_rt": "3.06",
                "ovrs_excg_cd": "NASD",
                "tr_crcy_cd": "USD",
            }],
            "output2": [{}],
        }
        # get_positions calls _session.get multiple times
        adapter._session.get = AsyncMock(side_effect=[domestic_resp, overseas_resp])
        positions = await adapter.get_positions()
        # Should have at least the overseas position
        assert any(p.symbol == "AAPL" for p in positions)

    @pytest.mark.asyncio
    async def test_submit_overseas_order_real_success(self):
        """Submit US stock order in live mode."""
        from agentic_capital.ports.trading import Market
        adapter = self._make_adapter(is_paper=False)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": {"ODNO": "OVERSEAS123", "KRX_FWDG_ORD_ORGNO": "ORG001"},
        }
        adapter._session.post = AsyncMock(return_value=mock_response)

        order = Order(
            symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=5, price=185.0, market=Market.US_STOCK, exchange="NASD",
        )
        result = await adapter.submit_order(order)
        assert result.order_id == "OVERSEAS123"
        assert result.status == "submitted"

    @pytest.mark.asyncio
    async def test_cancel_order_success(self):
        """cancel_order returns True on success."""
        adapter = self._make_adapter(is_paper=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "0", "output": {"ODNO": "ORDER123"}}
        adapter._session.post = AsyncMock(return_value=mock_response)
        result = await adapter.cancel_order("ORDER123")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self):
        """cancel_order returns False when API reports error."""
        adapter = self._make_adapter(is_paper=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "2", "msg1": "주문 없음"}
        adapter._session.post = AsyncMock(return_value=mock_response)
        result = await adapter.cancel_order("INVALID")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_overseas_order_paper_raises(self):
        """cancel_overseas_order raises in paper mode."""
        adapter = self._make_adapter(is_paper=True)
        with pytest.raises(NotImplementedError, match="paper"):
            await adapter.cancel_overseas_order("ORDER123", "NASD", "AAPL")

    @pytest.mark.asyncio
    async def test_cancel_overseas_order_live(self):
        """cancel_overseas_order succeeds in live mode."""
        adapter = self._make_adapter(is_paper=False)
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "0", "output": {"ODNO": "OVS_ORDER"}}
        adapter._session.post = AsyncMock(return_value=mock_response)
        result = await adapter.cancel_overseas_order("OVS_ORDER", "NASD", "AAPL")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_fills_with_data(self):
        """get_fills parses filled orders correctly."""
        adapter = self._make_adapter(is_paper=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output1": [{
                "pdno": "005930",
                "sll_buy_dvsn_cd": "02",  # buy
                "tot_ccld_qty": "10",
                "avg_prvs": "70000",
                "odno": "ORDER456",
            }],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        fills = await adapter.get_fills()
        assert len(fills) == 1
        assert fills[0].symbol == "005930"
        assert fills[0].quantity == 10.0
        assert fills[0].status == "filled"

    @pytest.mark.asyncio
    async def test_get_fills_skips_zero_quantity(self):
        """get_fills skips items with zero quantity."""
        adapter = self._make_adapter(is_paper=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output1": [
                {"pdno": "005930", "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "0", "avg_prvs": "70000", "odno": "O1"},
                {"pdno": "000660", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "5", "avg_prvs": "130000", "odno": "O2"},
            ],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        fills = await adapter.get_fills()
        assert len(fills) == 1
        assert fills[0].symbol == "000660"

    @pytest.mark.asyncio
    async def test_submit_futures_order_paper_rejects(self):
        """Futures orders return rejected when API not available in paper mode."""
        from agentic_capital.ports.trading import Market
        adapter = self._make_adapter(is_paper=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "2", "msg1": "선물 주문 불가"}
        adapter._session.post = AsyncMock(return_value=mock_response)
        order = Order(
            symbol="101V6000", side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=1, price=400.0, market=Market.KR_FUTURES,
        )
        result = await adapter.submit_order(order)
        assert result.status == "rejected"


class TestKISTradingAdapterOrderStatus:
    """Tests for get_order_status with found order."""

    def _make_adapter(self, *, is_paper: bool = True) -> KISTradingAdapter:
        session = _make_session(is_paper=is_paper)
        session._access_token = "token"
        return KISTradingAdapter(session=session)

    @pytest.mark.asyncio
    async def test_get_order_status_found_filled(self):
        """get_order_status returns filled when ccld_qty >= ord_qty."""
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output1": [{
                "odno": "ORDER456",
                "pdno": "005930",
                "sll_buy_dvsn_cd": "02",  # buy
                "tot_ccld_qty": "10",
                "ord_qty": "10",
                "avg_prvs": "70000",
            }],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        result = await adapter.get_order_status("ORDER456")
        assert result.status == "filled"
        assert result.symbol == "005930"

    @pytest.mark.asyncio
    async def test_get_order_status_found_partial(self):
        """get_order_status returns partial when partially filled."""
        adapter = self._make_adapter()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output1": [{
                "odno": "ORDER789",
                "pdno": "000660",
                "sll_buy_dvsn_cd": "01",  # sell
                "tot_ccld_qty": "5",
                "ord_qty": "10",
                "avg_prvs": "130000",
            }],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        result = await adapter.get_order_status("ORDER789")
        assert result.status == "partial"
        assert result.side.value == "sell"

    @pytest.mark.asyncio
    async def test_get_overseas_fills(self):
        """get_overseas_fills parses overseas fill correctly."""
        adapter = self._make_adapter(is_paper=False)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output1": [{
                "pdno": "AAPL",
                "sll_buy_dvsn_cd": "02",
                "ft_ccld_qty": "5",
                "ft_ccld_unpr3": "185.50",
                "odno": "OVS_ORDER123",
                "ovrs_excg_cd": "NASD",
                "tr_crcy_cd": "USD",
            }],
        }
        adapter._session.get = AsyncMock(return_value=mock_response)
        fills = await adapter.get_overseas_fills()
        assert len(fills) == 1
        assert fills[0].symbol == "AAPL"
        assert fills[0].filled_price == 185.5
        assert fills[0].market.value == "us_stock"

    @pytest.mark.asyncio
    async def test_get_overseas_fills_paper_raises(self):
        """get_overseas_fills raises in paper mode."""
        adapter = self._make_adapter(is_paper=True)
        with pytest.raises(NotImplementedError, match="paper"):
            await adapter.get_overseas_fills()
