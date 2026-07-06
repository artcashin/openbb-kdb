"""Tests for openbb_kdb.models.historical — pure helper functions."""

from datetime import date

import pytest

from openbb_core.app.model.abstract.error import OpenBBError

from openbb_kdb.models.historical import (
    _ohlcv_agg,
    _pandas_rule,
    _validate,
)


# ============================================================
# _pandas_rule
# ============================================================

class TestPandasRule:
    def test_1d(self):
        assert _pandas_rule("1d") == "1D"

    def test_1h(self):
        assert _pandas_rule("1h") == "1h"

    def test_5m(self):
        assert _pandas_rule("5m") == "5min"

    def test_30m(self):
        assert _pandas_rule("30m") == "30min"

    def test_1s(self):
        assert _pandas_rule("1s") == "1s"

    def test_1w(self):
        assert _pandas_rule("1w") == "1W"

    def test_2w(self):
        assert _pandas_rule("2w") == "2W"

    def test_1mo(self):
        assert _pandas_rule("1mo") == "1ME"

    def test_3mo(self):
        assert _pandas_rule("3mo") == "3ME"

    def test_capital_M_month(self):
        assert _pandas_rule("1M") == "1ME"

    def test_day_full(self):
        assert _pandas_rule("1day") == "1D"

    def test_minute_full(self):
        assert _pandas_rule("1minute") == "1min"

    def test_hour_full(self):
        assert _pandas_rule("2hour") == "2h"

    def test_week_full(self):
        assert _pandas_rule("1week") == "1W"

    def test_empty_interval(self):
        with pytest.raises(OpenBBError, match="Could not parse"):
            _pandas_rule("")

    def test_garbage_interval(self):
        with pytest.raises(OpenBBError, match="Could not parse"):
            _pandas_rule("not_an_interval")

    def test_unrecognized_unit(self):
        with pytest.raises(OpenBBError, match="Unsupported interval"):
            _pandas_rule("1y")

    def test_numeric_only_interval(self):
        with pytest.raises(OpenBBError, match="Could not parse"):
            _pandas_rule("123")

    def test_whitespace_handling(self):
        assert _pandas_rule("  1d  ") == "1D"

    def test_without_number(self):
        assert _pandas_rule("d") == "1D"

    def test_without_number_h(self):
        assert _pandas_rule("h") == "1h"


# ============================================================
# _ohlcv_agg
# ============================================================

class TestOhlcvAgg:
    def test_ohlc_columns(self):
        cols = ["open", "high", "low", "close", "volume"]
        spec = _ohlcv_agg(cols)
        assert spec["open"] == ("open", "first")
        assert spec["high"] == ("high", "max")
        assert spec["low"] == ("low", "min")
        assert spec["close"] == ("close", "last")
        assert spec["volume"] == ("volume", "sum")

    def test_ohlc_no_volume(self):
        cols = ["open", "high", "low", "close"]
        spec = _ohlcv_agg(cols)
        assert "volume" not in spec

    def test_mixed_case_columns(self):
        cols = ["Open", "High", "Low", "Close", "Volume"]
        spec = _ohlcv_agg(cols)
        assert spec["open"] == ("Open", "first")
        assert spec["volume"] == ("Volume", "sum")

    def test_price_column_only(self):
        cols = ["price", "size"]
        spec = _ohlcv_agg(cols)
        assert spec["open"] == ("price", "first")
        assert spec["close"] == ("price", "last")
        assert spec["volume"] == ("size", "sum")

    def test_price_column_variants(self):
        for price_col in ("last", "trade_price", "p"):
            cols = [price_col, "qty"]
            spec = _ohlcv_agg(cols)
            assert spec["close"] == (price_col, "last")

    def test_volume_column_variants(self):
        for vol_col in ("size", "qty", "quantity", "amount", "v"):
            cols = ["price", vol_col]
            spec = _ohlcv_agg(cols)
            assert spec["volume"] == (vol_col, "sum")

    def test_no_recognizable_price(self):
        cols = ["foo", "bar"]
        with pytest.raises(OpenBBError, match="Cannot resample"):
            _ohlcv_agg(cols)

    def test_empty_columns(self):
        with pytest.raises(OpenBBError, match="Cannot resample"):
            _ohlcv_agg([])


# ============================================================
# _validate
# ============================================================

@pytest.fixture
def sample_data():
    return [
        {"date": "2026-01-02", "open": 150.0, "close": 152.0},
        {"date": "2026-01-03", "open": 151.0, "close": float("nan")},
        {"date": "2026-01-06", "open": None, "close": 154.0},
    ]


class TestValidate:
    def test_sorted_by_date(self, sample_data):
        # Use a fake data_cls that accepts all fields
        from pydantic import BaseModel

        class FakeData(BaseModel):
            date: date
            open: float | None = None
            close: float | None = None

        results = _validate(None, sample_data, FakeData)
        dates = [r.date for r in results]
        assert dates == sorted(dates)

    def test_nan_stripped(self, sample_data):
        from pydantic import BaseModel

        class FakeData(BaseModel):
            date: date
            open: float | None = None
            close: float | None = None

        results = _validate(None, sample_data, FakeData)
        row = [r for r in results if r.date == date(2026, 1, 3)][0]
        # NaN should be None after validation
        assert row.close is None

    def test_none_kept(self, sample_data):
        from pydantic import BaseModel

        class FakeData(BaseModel):
            date: date
            open: float | None = None
            close: float | None = None

        results = _validate(None, sample_data, FakeData)
        row = [r for r in results if r.date == date(2026, 1, 6)][0]
        assert row.open is None

    def test_empty_data_list(self):
        from pydantic import BaseModel
        from typing import Optional

        class FakeData(BaseModel):
            date: Optional[date] = None

        results = _validate(None, [], FakeData)
        assert results == []
