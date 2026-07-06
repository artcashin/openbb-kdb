"""Tests for openbb_kdb.utils — pure functions with no external deps."""

from datetime import date, datetime

import pandas as pd
import pytest

from openbb_kdb.utils import (
    close_connection,
    normalize_index,
    parse_temporal,
    resolve_config,
    table_name,
    to_bounds,
)


# ============================================================
# resolve_config
# ============================================================

class TestResolveConfig:
    def test_defaults(self):
        host, port, user, password = resolve_config()
        assert host == "localhost"
        assert port == 5000
        assert user is None
        assert password is None

    def test_explicit_args_win(self):
        host, port, user, password = resolve_config(
            host="myhost", port=9999, user="u", password="p"
        )
        assert host == "myhost"
        assert port == 9999
        assert user == "u"
        assert password == "p"

    def test_credentials_dict(self):
        creds = {
            "kdb_host": "credhost",
            "kdb_port": "6000",
            "kdb_user": "cuser",
            "kdb_password": "cpass",
        }
        host, port, user, password = resolve_config(credentials=creds)
        assert host == "credhost"
        assert port == 6000
        assert user == "cuser"
        assert password == "cpass"

    def test_explicit_overrides_creds(self):
        creds = {"kdb_host": "credhost", "kdb_port": "6000"}
        host, port, _, _ = resolve_config(host="explicit", credentials=creds)
        assert host == "explicit"
        assert port == 6000

    def test_env_vars(self, monkeypatch):
        monkeypatch.setenv("KDB_HOST", "envhost")
        monkeypatch.setenv("KDB_PORT", "7000")
        monkeypatch.setenv("KDB_USER", "evuser")
        monkeypatch.setenv("KDB_PASSWORD", "evpass")
        host, port, user, password = resolve_config()
        assert host == "envhost"
        assert port == 7000
        assert user == "evuser"
        assert password == "evpass"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("KDB_HOST", "envhost")
        monkeypatch.setenv("KDB_PORT", "7000")
        host, port, _, _ = resolve_config(host="myhost", port=8000)
        assert host == "myhost"
        assert port == 8000

    def test_port_string(self):
        _, port, _, _ = resolve_config(port="1234")
        assert port == 1234

    def test_port_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid kdb\\+ port"):
            resolve_config(port="abc")

    def test_port_out_of_range_low(self):
        with pytest.raises(ValueError, match="out of range"):
            resolve_config(port=0)

    def test_port_out_of_range_high(self):
        with pytest.raises(ValueError, match="out of range"):
            resolve_config(port=65536)


# ============================================================
# table_name
# ============================================================

class TestTableName:
    def test_simple(self):
        assert table_name("AAPL") == "AAPL"

    def test_sanitize_special_chars(self):
        assert table_name("ABC.DEF") == "ABC_DEF"

    def test_sanitize_spaces(self):
        assert table_name("BITCOIN CASH") == "BITCOIN_CASH"

    def test_non_alpha_start(self):
        assert table_name("123abc") == "t_123abc"

    def test_non_alpha_start_underscore(self):
        assert table_name("_abc") == "t__abc"

    def test_empty_string(self):
        result = table_name("")
        assert result.startswith("t_")

    def test_q_keyword_select(self):
        assert table_name("select") == "t_select"

    def test_q_keyword_delete(self):
        assert table_name("delete") == "t_delete"

    def test_q_keyword_case_insensitive(self):
        assert table_name("SELECT") == "t_SELECT"

    def test_q_keyword_where(self):
        assert table_name("where") == "t_where"

    def test_q_keyword_by(self):
        assert table_name("by") == "t_by"

    def test_whitespace_stripped(self):
        assert table_name("  AAPL  ") == "AAPL"


# ============================================================
# parse_temporal
# ============================================================

class TestParseTemporal:
    def test_none(self):
        assert parse_temporal(None) is None

    def test_datetime_preserved(self):
        dt = datetime(2026, 1, 15, 10, 30, 0)
        assert parse_temporal(dt) is dt

    def test_date_preserved(self):
        d = date(2026, 1, 15)
        assert parse_temporal(d) is d

    def test_string_date(self):
        result = parse_temporal("2026-01-15")
        assert isinstance(result, date)
        assert not isinstance(result, datetime)
        assert result == date(2026, 1, 15)

    def test_string_datetime(self):
        result = parse_temporal("2026-01-15T10:30:00")
        assert isinstance(result, datetime)
        assert result == datetime(2026, 1, 15, 10, 30, 0)

    def test_string_datetime_iso(self):
        result = parse_temporal("2026-01-15 10:30:00")
        assert isinstance(result, datetime)

    def test_non_string_non_date(self):
        assert parse_temporal(42) == 42


# ============================================================
# to_bounds
# ============================================================

class TestToBounds:
    def test_none(self):
        start, end = to_bounds(None, None)
        assert start is None
        assert end is None

    def test_date_range(self):
        start, end = to_bounds("2026-01-02", "2026-01-06")
        assert start is not None
        assert end is not None
        assert start <= end

    def test_end_date_becomes_end_of_day(self):
        _, end = to_bounds(None, "2026-01-06")
        assert end is not None
        assert end.hour == 23
        assert end.minute == 59
        assert end.second == 59

    def test_datetime_preserved(self):
        _, end = to_bounds(None, datetime(2026, 1, 6, 10, 0, 0))
        assert end is not None
        assert end.hour == 10

    def test_start_only(self):
        start, end = to_bounds("2026-01-02", None)
        assert start is not None
        assert end is None


# ============================================================
# normalize_index
# ============================================================

class TestNormalizeIndex:
    def test_datetime_index_sorted(self):
        df = pd.DataFrame({"val": [3, 1, 2]},
                          index=pd.DatetimeIndex(["2026-01-06", "2026-01-02", "2026-01-03"]))
        result = normalize_index(df)
        assert isinstance(result.index, pd.DatetimeIndex)
        assert list(result.index) == [
            pd.Timestamp("2026-01-02"),
            pd.Timestamp("2026-01-03"),
            pd.Timestamp("2026-01-06"),
        ]
        assert list(result["val"]) == [1, 2, 3]

    def test_date_column_sets_index(self):
        df = pd.DataFrame({"date": ["2026-01-03", "2026-01-02"], "val": [1, 2]})
        result = normalize_index(df)
        assert isinstance(result.index, pd.DatetimeIndex)
        assert result.index.name == "date"

    def test_time_column(self):
        df = pd.DataFrame({
            "time": [datetime(2026, 1, 2, 9, 30), datetime(2026, 1, 2, 9, 31)],
            "val": [1, 2],
        })
        result = normalize_index(df)
        assert isinstance(result.index, pd.DatetimeIndex)

    def test_range_index_unchanged(self):
        df = pd.DataFrame({"val": [1, 2]})
        result = normalize_index(df)
        assert isinstance(result.index, pd.RangeIndex)

    def test_numeric_index_unchanged(self):
        df = pd.DataFrame({"val": [1, 2]}, index=pd.Index([10, 20]))
        result = normalize_index(df)
        assert result.index.dtype == "int64" or pd.api.types.is_numeric_dtype(result.index)


# ============================================================
# close_connection
# ============================================================

class TestCloseConnection:
    def test_close_called_on_mock(self):
        calls = []
        class FakeConn:
            def close(self):
                calls.append("close")
        close_connection(FakeConn())
        assert calls == ["close"]

    def test_close_swallows_error(self):
        class BadConn:
            def close(self):
                raise RuntimeError("boom")
        close_connection(BadConn())  # should not raise

    def test_close_does_not_swallow_keyboard_interrupt(self):
        class InterruptConn:
            def close(self):
                raise KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            close_connection(InterruptConn())

    def test_close_does_not_swallow_system_exit(self):
        class ExitConn:
            def close(self):
                raise SystemExit(1)
        with pytest.raises(SystemExit):
            close_connection(ExitConn())
