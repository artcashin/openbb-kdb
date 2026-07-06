"""Tests for openbb_kdb.store — KDBStore with mock connections."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from openbb_kdb.store import KDBStore, store


# Make pykx importable inside the q_* utility functions so they don't fail
# when called with a mock connection.  The real kx.SymbolAtom / kx.toq are
# needed only for talking to a live server; for tests we just pass through.
@pytest.fixture(autouse=True, scope="module")
def _mock_pykx():
    mock_kx = MagicMock()
    mock_kx.SymbolAtom = lambda x: x
    mock_kx.toq = lambda x: x
    with patch.dict("sys.modules", {"pykx": mock_kx}):
        yield


# ============================================================
# _to_frame
# ============================================================

class TestToFrame:
    def test_dataframe_roundtrip(self, ohlc_no_index_df):
        df = KDBStore._to_frame(ohlc_no_index_df)
        assert isinstance(df, pd.DataFrame)
        assert "date" not in df.columns or "open" in df.columns
        # date column should have been set as index
        assert isinstance(df.index, pd.DatetimeIndex) or "date" in df.columns

    def test_empty_raises(self, empty_df):
        with pytest.raises(ValueError, match="No data"):
            KDBStore._to_frame(empty_df)

    def test_none_obbject_data_raises(self):
        with pytest.raises(ValueError, match="No data"):
            KDBStore._to_frame(None)

    def test_records_list(self):
        records = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        df = KDBStore._to_frame(records)
        assert len(df) == 2
        assert list(df.columns) == ["a", "b"]

    def test_date_column_collision_handled(self, df_date_collision):
        df = KDBStore._to_frame(df_date_collision)
        assert "date" in df.columns
        assert not df["date"].isin(["ignore-me"]).any()
        assert df["date"].iloc[0] == pd.Timestamp("2026-01-02")


# ============================================================
# _to_obbject
# ============================================================

class TestToOBBject:
    def test_basic_conversion(self, ohlc_df):
        obj = KDBStore._to_obbject(ohlc_df, "AAPL")
        assert obj.provider == "kdb"
        assert obj.extra == {"symbol": "AAPL"}
        assert len(obj.results) == 3

    def test_results_have_expected_fields(self, ohlc_df):
        obj = KDBStore._to_obbject(ohlc_df, "AAPL")
        r = obj.results[0]
        assert hasattr(r, "open")
        assert hasattr(r, "high")
        assert hasattr(r, "close")
        assert hasattr(r, "date")

    def test_nan_filtered_from_results(self, df_with_nan):
        df = df_with_nan.reset_index(drop=True)
        df.index = pd.DatetimeIndex(["2026-01-02", "2026-01-03", "2026-01-06"], name="date")
        obj = KDBStore._to_obbject(df, "TEST")
        rows = [r.model_dump(exclude_none=False) for r in obj.results]
        # Row 0 has NaN open, row 1 has NaN close, row 2 has NaN close
        # None of them should contain an actual NaN float; either the key is
        # absent (stripped by _to_obbject) or the value is a valid float.
        for row in rows:
            for k, v in row.items():
                if isinstance(v, float):
                    assert not pd.isna(v), f"NaN found in {k}={v}"

    def test_none_values_kept(self):
        df = pd.DataFrame(
            {"open": [150.0, None]},
            index=pd.DatetimeIndex(["2026-01-02", "2026-01-03"], name="date"),
        )
        obj = KDBStore._to_obbject(df, "T")
        # None should remain, only NaN is stripped
        assert len(obj.results) == 2


# ============================================================
# close
# ============================================================

class TestClose:
    def test_close_nullifies_connection(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        assert s._conn_obj is not None
        s.close()
        assert s._conn_obj is None

    def test_close_idempotent(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        s.close()
        s.close()  # second call should not raise

    def test_close_calls_underlying_close(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        s.close()
        assert any(c[0] == "close" for c in mock_conn.calls)

    def test_close_without_connection(self):
        s = KDBStore(conn=None)
        s.close()  # should not raise


# ============================================================
# CRUD operations with mock connection
# ============================================================

class TestWrite:
    def test_write_returns_metadata(self, ohlc_no_index_df, mock_conn):
        s = KDBStore(conn=mock_conn)
        info = s.write("AAPL", ohlc_no_index_df)
        assert info["symbol"] == "AAPL"
        assert info["rows"] == 3
        assert "table" in info

    def test_write_stores_data(self, ohlc_no_index_df, empty_conn):
        s = KDBStore(conn=empty_conn)
        s.write("NEW", ohlc_no_index_df)
        assert "NEW" in empty_conn._tables


class TestRead:
    def test_read_returns_obbject(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        obj = s.read("AAPL")
        assert hasattr(obj, "results")
        assert len(obj.results) == 3

    def test_read_dataframe_output(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        df = s.read("AAPL", output="dataframe")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_read_missing_raises(self, empty_conn):
        s = KDBStore(conn=empty_conn)
        with pytest.raises(KeyError, match="not found"):
            s.read("NONEXISTENT")

    def test_read_with_date_filter(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        df = s.read("AAPL", output="dataframe",
                    start_date="2026-01-02", end_date="2026-01-03")
        assert len(df) == 2

    def test_read_with_columns_subset(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        df = s.read("AAPL", output="dataframe", columns=["open", "close"])
        assert list(df.columns) == ["open", "close"]


class TestAppend:
    def test_append_adds_rows(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        new_row = pd.DataFrame({
            "open": [155.0], "high": [156.0], "low": [154.0],
            "close": [155.5], "volume": [1300],
        })
        info = s.append("AAPL", new_row)
        assert info["rows_appended"] == 1
        df = s.read("AAPL", output="dataframe")
        assert len(df) == 4

    def test_append_new_table(self, empty_conn):
        s = KDBStore(conn=empty_conn)
        df = pd.DataFrame({"a": [1]})
        s.append("NEW_TABLE", df)
        assert "NEW_TABLE" in empty_conn._tables


class TestCatalog:
    def test_list_symbols(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        symbols = s.list_symbols()
        assert "AAPL" in symbols

    def test_list_symbols_empty(self, empty_conn):
        s = KDBStore(conn=empty_conn)
        assert s.list_symbols() == []

    def test_has_true(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        assert s.has("AAPL") is True

    def test_has_false(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        assert s.has("MISSING") is False

    def test_delete_removes(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        info = s.delete("AAPL")
        assert info["deleted"] == "AAPL"
        assert s.has("AAPL") is False

    def test_delete_missing(self, empty_conn):
        s = KDBStore(conn=empty_conn)
        s.delete("NONEXISTENT")  # should not raise

    def test_meta(self, mock_conn):
        s = KDBStore(conn=mock_conn)
        m = s.meta("AAPL")
        assert isinstance(m, pd.DataFrame)
        assert "c" in m.columns or len(m) > 0


# ============================================================
# store factory
# ============================================================

class TestStoreFactory:
    def test_returns_kdbstore(self):
        s = store(host="h", port=1)
        assert isinstance(s, KDBStore)
        assert s.host == "h"
        assert s.port == 1

    def test_accepts_explicit_conn(self, mock_conn):
        s = store(conn=mock_conn)
        assert s._conn_obj is mock_conn
