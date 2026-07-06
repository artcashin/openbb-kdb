"""Shared fixtures for openbb-kdb tests."""

from datetime import datetime

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Sample DataFrames
# ---------------------------------------------------------------------------

@pytest.fixture
def ohlc_df():
    """Daily OHLCV DataFrame with a DatetimeIndex."""
    idx = pd.DatetimeIndex(
        ["2026-01-02", "2026-01-03", "2026-01-06"],
        name="date",
    )
    return pd.DataFrame(
        {
            "open": [150.0, 151.0, 152.0],
            "high": [153.0, 154.0, 155.0],
            "low": [149.0, 150.0, 151.0],
            "close": [152.0, 153.0, 154.0],
            "volume": [1000, 1100, 1200],
        },
        index=idx,
    )


@pytest.fixture
def ohlc_no_index_df():
    """OHLCV data with a 'date' column instead of an index."""
    return pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-03", "2026-01-06"],
            "open": [150.0, 151.0, 152.0],
            "high": [153.0, 154.0, 155.0],
            "low": [149.0, 150.0, 151.0],
            "close": [152.0, 153.0, 154.0],
            "volume": [1000, 1100, 1200],
        }
    )


@pytest.fixture
def tick_df():
    """Tick data with a 'time' column."""
    return pd.DataFrame(
        {
            "time": [
                datetime(2026, 1, 2, 9, 30, 5),
                datetime(2026, 1, 2, 9, 30, 10),
                datetime(2026, 1, 2, 9, 30, 15),
            ],
            "price": [150.0, 151.0, 150.5],
            "size": [100, 200, 150],
        }
    )


@pytest.fixture
def df_with_nan():
    """DataFrame with NaN values."""
    return pd.DataFrame(
        {
            "open": [150.0, float("nan"), 152.0],
            "close": [152.0, 153.0, float("nan")],
            "volume": [1000, 1100, 1200],
        }
    )


@pytest.fixture
def empty_df():
    """Empty DataFrame."""
    return pd.DataFrame()


@pytest.fixture
def df_date_collision():
    """DataFrame with both a DatetimeIndex named 'date' AND a 'date' column."""
    df = pd.DataFrame(
        {
            "date": ["ignore-me"],
            "open": [150.0],
            "close": [152.0],
        }
    )
    df.index = pd.DatetimeIndex(["2026-01-02"], name="date")
    return df


# ---------------------------------------------------------------------------
# Mock PyKX connection
# ---------------------------------------------------------------------------

class MockQConnection:
    """Callable mock that records q calls and returns canned DataFrames."""

    def __init__(self, tables: dict | None = None):
        self.calls: list[tuple] = []
        self._tables: dict[str, pd.DataFrame] = {}
        if tables:
            for k, v in tables.items():
                self._tables[k] = v

    def set_table(self, name: str, df: pd.DataFrame):
        self._tables[name] = df

    def __call__(self, cmd, *args):
        self.calls.append((cmd, args))
        name = str(args[0]) if args else None

        if cmd == "get" and name in self._tables:
            return _TableWrapper(self._tables[name])
        if cmd == "set":
            self._tables[name] = args[1] if len(args) > 1 else pd.DataFrame()
            return None
        if cmd == "upsert":
            if name in self._tables:
                self._tables[name] = pd.concat(
                    [self._tables[name], args[1]], ignore_index=True
                )
            else:
                self._tables[name] = args[1]
            return None
        if cmd == "tables[`.]":
            return _ListWrapper(list(self._tables.keys()))
        if isinstance(cmd, str) and "in tables" in cmd:
            return _BoolWrapper(name in self._tables)
        if cmd == "meta":
            if name in self._tables:
                return _TableWrapper(_meta_from_df(self._tables[name]))
            return _TableWrapper(pd.DataFrame())
        if isinstance(cmd, str) and "!" in cmd:
            if name in self._tables:
                del self._tables[name]
            return None
        return None

    def close(self):
        self.calls.append(("close", ()))


class _TableWrapper:
    """Wraps a DataFrame so it looks like a PyKX Table (has .pd())."""

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def pd(self) -> pd.DataFrame:
        return self._df


class _ListWrapper:
    """Wraps a list so it looks like a PyKX result (has .py())."""

    def __init__(self, items: list):
        self._items = items

    def py(self) -> list:
        return self._items


class _BoolWrapper:
    """Wraps a bool so it looks like a PyKX result (has .py())."""

    def __init__(self, val: bool):
        self._val = val

    def py(self) -> bool:
        return self._val


def _meta_from_df(df: pd.DataFrame) -> pd.DataFrame:
    """Build a q-meta-like DataFrame from a pandas DataFrame."""
    type_map = {v: "f" for v in df.select_dtypes(include="float").columns}
    type_map.update({v: "j" for v in df.select_dtypes(include="int").columns})
    type_map.update({v: "s" for v in df.select_dtypes(include="object").columns})
    type_map.update({v: "z" for v in df.select_dtypes(include="datetime").columns})
    return pd.DataFrame(
        {
            "c": list(df.columns),
            "t": [type_map.get(c, " ") for c in df.columns],
            "a": [" " for _ in df.columns],
            "f": ["" for _ in df.columns],
        }
    )


@pytest.fixture
def mock_conn(ohlc_df):
    """A MockQConnection pre-loaded with a table called 'AAPL'."""
    return MockQConnection(tables={"AAPL": ohlc_df})


@pytest.fixture
def empty_conn():
    """A MockQConnection with no tables."""
    return MockQConnection()
