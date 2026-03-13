"""Tests for AI-friendly data format converters."""

import pytest

from agentic_capital.formats.markdown_kv import from_markdown_kv, to_markdown_kv
from agentic_capital.formats.numerologic import from_numerologic, to_numerologic
from agentic_capital.formats.toon import from_toon, to_toon


class TestTOON:
    def test_basic_conversion(self) -> None:
        result = to_toon("prices", ["ticker", "close"], [["AAPL", "+0.8"]])
        assert result == "@prices[1](ticker,close)\nAAPL,+0.8"

    def test_multiple_rows(self) -> None:
        rows = [["AAPL", "+0.8"], ["GOOG", "-0.3"]]
        result = to_toon("prices", ["ticker", "close"], rows)
        assert "@prices[2]" in result
        assert "AAPL,+0.8" in result
        assert "GOOG,-0.3" in result

    def test_roundtrip(self) -> None:
        columns = ["ticker", "close", "vol"]
        rows = [["AAPL", "+0.8", "1.1x"], ["GOOG", "-0.3", "0.9x"]]
        toon_str = to_toon("prices", columns, rows)
        name, parsed_cols, parsed_rows = from_toon(toon_str)
        assert name == "prices"
        assert parsed_cols == columns
        assert parsed_rows == rows

    def test_empty_rows(self) -> None:
        result = to_toon("empty", ["a", "b"], [])
        assert "@empty[0]" in result


class TestNumeroLogic:
    def test_integer(self) -> None:
        assert to_numerologic(12345) == "{5:12345}"

    def test_decimal(self) -> None:
        result = to_numerologic(0.05)
        assert ":0.05}" in result

    def test_negative(self) -> None:
        result = to_numerologic(-42)
        assert ":-42}" in result

    def test_from_numerologic(self) -> None:
        assert from_numerologic("{5:12345}") == 12345.0
        assert from_numerologic("{4:0.05}") == 0.05

    def test_roundtrip(self) -> None:
        for val in [100, 0.5, 12345, 0.001]:
            encoded = to_numerologic(val)
            decoded = from_numerologic(encoded)
            assert decoded == pytest.approx(val)

    def test_invalid_format(self) -> None:
        with pytest.raises(ValueError):
            from_numerologic("not_valid")


class TestMarkdownKV:
    def test_basic_conversion(self) -> None:
        data = {"ticker": "AAPL", "signal": "BUY"}
        result = to_markdown_kv(data)
        assert "ticker: AAPL" in result
        assert "signal: BUY" in result

    def test_roundtrip(self) -> None:
        data = {"ticker": "AAPL", "signal": "BUY", "confidence": "0.72"}
        result = from_markdown_kv(to_markdown_kv(data))
        assert result == data

    def test_from_markdown_kv(self) -> None:
        text = "ticker: AAPL\nsignal: BUY\nconfidence: 0.72"
        result = from_markdown_kv(text)
        assert result["ticker"] == "AAPL"
        assert result["confidence"] == "0.72"
