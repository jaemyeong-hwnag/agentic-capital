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
    async def test_get_symbols(self):
        adapter = self._make_adapter()
        symbols = await adapter.get_symbols()
        assert "005930" in symbols
        assert len(symbols) == 10

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
