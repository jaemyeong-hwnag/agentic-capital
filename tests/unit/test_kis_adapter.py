"""Unit tests for KIS trading and market data adapters."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.adapters.trading.kis import KISTradingAdapter
from agentic_capital.adapters.market_data.kis import KISMarketDataAdapter
from agentic_capital.ports.trading import Order, OrderSide, OrderType


class TestKISTradingAdapter:
    """Test KISTradingAdapter initialization and URL selection."""

    def test_init_requires_credentials(self):
        with patch("agentic_capital.adapters.trading.kis.settings") as mock_s:
            mock_s.kis_app_key = ""
            mock_s.kis_app_secret = ""
            mock_s.kis_account_no = ""
            mock_s.kis_is_paper = True
            with pytest.raises(ValueError, match="KIS_APP_KEY"):
                KISTradingAdapter()

    def test_init_paper_mode(self):
        with patch("agentic_capital.adapters.trading.kis.settings") as mock_s:
            mock_s.kis_app_key = "key"
            mock_s.kis_app_secret = "secret"
            mock_s.kis_account_no = "5017463701"
            mock_s.kis_is_paper = True
            adapter = KISTradingAdapter()
            assert "openapivts" in adapter._base_url
            assert adapter._cano == "50174637"
            assert adapter._prdt_cd == "01"

    def test_init_live_mode(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=False
        )
        assert "openapi.koreainvestment" in adapter._base_url
        assert adapter._is_paper is False

    def test_tr_id_paper(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        assert adapter._tr_id("balance") == "VTTC8434R"
        assert adapter._tr_id("order_buy") == "VTTC0802U"

    def test_tr_id_live(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=False
        )
        assert adapter._tr_id("balance") == "TTTC8434R"
        assert adapter._tr_id("order_sell") == "TTTC0801U"


    @pytest.mark.asyncio
    async def test_ensure_token(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "test-token-123"}
        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_response)

        token = await adapter._ensure_token()
        assert token == "test-token-123"
        assert adapter._access_token == "test-token-123"

    @pytest.mark.asyncio
    async def test_ensure_token_cached(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "cached-token"
        token = await adapter._ensure_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_ensure_token_failure(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"error_code": "EGW00133"}
        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="KIS token failed"):
            await adapter._ensure_token()

    @pytest.mark.asyncio
    async def test_get_balance(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "token"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output2": [{"tot_evlu_amt": "10000000", "dnca_tot_amt": "5000000"}],
        }
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)

        balance = await adapter.get_balance()
        assert balance.total == 10_000_000.0
        assert balance.available == 5_000_000.0
        assert balance.currency == "KRW"

    @pytest.mark.asyncio
    async def test_get_balance_error(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "token"
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "2", "msg1": "INVALID"}
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="KIS balance failed"):
            await adapter.get_balance()

    @pytest.mark.asyncio
    async def test_get_positions_empty(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "token"
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "0", "output1": []}
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)

        positions = await adapter.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_with_data(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "token"
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
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)

        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "005930"
        assert positions[0].quantity == 10.0

    @pytest.mark.asyncio
    async def test_submit_order_success(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "token"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output": {"ODNO": "ORDER123"},
        }
        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_response)

        order = Order(symbol="005930", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=70000)
        result = await adapter.submit_order(order)
        assert result.order_id == "ORDER123"
        assert result.status == "submitted"

    @pytest.mark.asyncio
    async def test_submit_order_rejected(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "token"
        mock_response = MagicMock()
        mock_response.json.return_value = {"rt_cd": "2", "msg1": "잔고 부족"}
        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_response)

        order = Order(symbol="005930", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
        result = await adapter.submit_order(order)
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_get_order_status(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        result = await adapter.get_order_status("ORDER123")
        assert result.order_id == "ORDER123"
        assert result.status == "unknown"

    @pytest.mark.asyncio
    async def test_get_quote(self):
        adapter = KISTradingAdapter(
            app_key="k", app_secret="s", account_no="1234567890", is_paper=True
        )
        adapter._access_token = "token"
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
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)

        quote = await adapter.get_quote("005930")
        assert quote["price"] == 72000
        assert quote["change"] == 1000


class TestKISMarketDataAdapter:
    """Test KISMarketDataAdapter."""

    def test_init_paper(self):
        adapter = KISMarketDataAdapter(
            app_key="k", app_secret="s", is_paper=True
        )
        assert "openapivts" in adapter._base_url

    def test_init_live(self):
        adapter = KISMarketDataAdapter(
            app_key="k", app_secret="s", is_paper=False
        )
        assert "openapi.koreainvestment" in adapter._base_url

    @pytest.mark.asyncio
    async def test_get_symbols(self):
        adapter = KISMarketDataAdapter(
            app_key="k", app_secret="s", is_paper=True
        )
        symbols = await adapter.get_symbols()
        assert "005930" in symbols
        assert len(symbols) == 10

    @pytest.mark.asyncio
    async def test_get_quote(self):
        adapter = KISMarketDataAdapter(
            app_key="k", app_secret="s", is_paper=True
        )
        adapter._access_token = "token"
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
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)

        quote = await adapter.get_quote("005930")
        assert quote.price == 72000.0
        assert quote.symbol == "005930"

    @pytest.mark.asyncio
    async def test_get_ohlcv(self):
        adapter = KISMarketDataAdapter(
            app_key="k", app_secret="s", is_paper=True
        )
        adapter._access_token = "token"
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
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)

        candles = await adapter.get_ohlcv("005930", limit=10)
        assert len(candles) == 2
        assert candles[0].close == 72000.0
        assert candles[1].open == 70000.0
