"""kdb+ historical price models (read path).

Reads a q table (one per symbol) from a kdb+ server and serves it through the
standard OpenBB interface, resampling into OHLCV bars. Unlike ArcticDB, kdb has
no server-side OpenBB resampler here, so the table is fetched and resampled in
pandas (tick price/size -> OHLCV, or downsampled finer bars), with the same
interval / pandas_anchor / date+datetime semantics as openbb-arcticdb.
"""

import math

from datetime import date as dateType, datetime
from typing import Any, List, Optional, Union

from openbb_core.app.model.abstract.error import OpenBBError
from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.standard_models.crypto_historical import (
    CryptoHistoricalData,
    CryptoHistoricalQueryParams,
)
from openbb_core.provider.standard_models.currency_historical import (
    CurrencyHistoricalData,
    CurrencyHistoricalQueryParams,
)
from openbb_core.provider.standard_models.equity_historical import (
    EquityHistoricalData,
    EquityHistoricalQueryParams,
)
from openbb_core.provider.standard_models.etf_historical import (
    EtfHistoricalData,
    EtfHistoricalQueryParams,
)
from openbb_core.provider.standard_models.index_historical import (
    IndexHistoricalData,
    IndexHistoricalQueryParams,
)
from openbb_core.provider.utils.errors import EmptyDataError
from pydantic import Field, field_validator

_OHLC = (("open", "first"), ("high", "max"), ("low", "min"), ("close", "last"))


def _pandas_rule(interval: str) -> str:
    """Map an OpenBB interval to a pandas resample offset alias."""
    # pylint: disable=import-outside-toplevel
    import re

    s = str(interval).strip()
    m = re.fullmatch(r"(\d*)\s*([a-zA-Z]+)", s)
    if not m:
        raise OpenBBError(f"Could not parse interval '{interval}'.")
    n = m.group(1) or "1"
    raw = m.group(2)
    unit = raw.lower()
    if raw == "M" or unit in {"mo", "mon", "month", "months", "mth"}:
        return f"{n}ME"
    if unit in {"w", "wk", "week", "weeks"}:
        return f"{n}W"
    base = {
        "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
        "m": "min", "min": "min", "mins": "min", "minute": "min", "minutes": "min", "t": "min",
        "h": "h", "hr": "h", "hour": "h", "hours": "h",
        "d": "D", "day": "D", "days": "D",
    }.get(unit)
    if base is None:
        raise OpenBBError(
            f"Unsupported interval '{interval}'. Supported: seconds (s), minutes "
            "(m/min), hours (h), days (d), weeks (w), months (mo/M)."
        )
    return f"{n}{base}"


def _ohlcv_agg(columns) -> dict:
    """Named-aggregation spec {out: (col, func)} for OHLCV, from the table columns."""
    cl = {str(c).lower(): c for c in columns}
    if {"open", "high", "low", "close"} <= set(cl):
        spec = {k: (cl[k], fn) for k, fn in _OHLC}
        if "volume" in cl:
            spec["volume"] = (cl["volume"], "sum")
        return spec
    price = next((cl[c] for c in ("price", "last", "close", "trade_price", "p") if c in cl), None)
    if price is None:
        raise OpenBBError(
            "Cannot resample to OHLCV: table has neither OHLC columns nor a "
            "recognizable price column (price/last/close)."
        )
    spec = {k: (price, fn) for k, fn in _OHLC}
    vol = next((cl[c] for c in ("size", "volume", "qty", "quantity", "amount", "v") if c in cl), None)
    if vol is not None:
        spec["volume"] = (vol, "sum")
    return spec


def _read_sync(query, credentials: Optional[dict]) -> list[dict]:
    """Connect, fetch the table(s), filter by date, resample to OHLCV (pandas)."""
    # pylint: disable=import-outside-toplevel
    from pandas import DatetimeIndex

    from openbb_kdb.utils import (
        close_connection,
        get_connection,
        normalize_index,
        q_get,
        q_has,
        resolve_config,
        table_name,
        to_bounds,
    )

    host, port, user, password = resolve_config(
        getattr(query, "host", None), getattr(query, "port", None),
        getattr(query, "user", None), getattr(query, "password", None), credentials,
    )
    conn = get_connection(host, port, user, password)

    symbols = [s.strip() for s in (query.symbol or "").split(",") if s.strip()]
    multiple = len(symbols) > 1
    interval = getattr(query, "interval", None) or "1d"
    rule = _pandas_rule(interval)
    origin = "start_day" if bool(getattr(query, "pandas_anchor", False)) else "epoch"
    start_ts, end_ts = to_bounds(query.start_date, query.end_date)

    out: list[dict] = []
    missing: list[str] = []
    try:
        for sym in symbols:
            name = table_name(sym)
            if not q_has(conn, name):
                missing.append(sym)
                continue
            df = q_get(conn, name).pd()
            df = normalize_index(df)
            if isinstance(df.index, DatetimeIndex) and (start_ts is not None or end_ts is not None):
                lo = start_ts if start_ts is not None else df.index.min()
                hi = end_ts if end_ts is not None else df.index.max()
                df = df.loc[lo:hi]
            if df is None or df.empty:
                continue
            if isinstance(df.index, DatetimeIndex):
                # dropna on 'close' removes empty buckets (e.g. weekends) where sum()
                # volume is 0 but first/last OHLC are NaN.
                df = (
                    df.resample(rule, origin=origin)
                    .agg(**_ohlcv_agg(df.columns))
                    .dropna(subset=["close"])
                )
            df = df.reset_index()
            if "date" not in df.columns:
                df = df.rename(columns={df.columns[0]: "date"})
            records = df.to_dict("records")
            if multiple:
                for rec in records:
                    rec["symbol"] = sym
            out.extend(records)
    finally:
        close_connection(conn)

    if not out:
        detail = f" Unknown symbols: {missing}." if missing else ""
        raise EmptyDataError(f"No data in kdb+ on {host}:{port}.{detail}")
    return out


def _validate(query, data: list[dict], data_cls):
    results = []
    for rec in data:
        clean = {
            k: v for k, v in rec.items()
            if not (isinstance(v, float) and math.isnan(v))
        }
        results.append(data_cls.model_validate(clean))
    results.sort(key=lambda r: (str(getattr(r, "symbol", "")), r.date))
    return results


def _build_fetcher(label: str, qp_base, data_base):
    """Create a kdb+ Fetcher for a given OHLCV standard model."""

    class _QP(qp_base):  # type: ignore[valid-type, misc]
        # OpenBB core reads this dunder directly (registry_map / package_builder)
        # to enable multi-symbol; pydantic's model_config json_schema_extra is a
        # different mechanism core never inspects, so it must stay this attribute.
        __json_schema_extra__ = {"symbol": {"multiple_items_allowed": True}}
        interval: Optional[str] = Field(
            default=None,
            description=(
                "Resample the table into OHLCV bars: seconds (1s), minutes "
                "(1m/5m), hours (1h), days (1d), weeks (1w/2w), months "
                "(1mo/3mo or 1M/3M). Defaults to '1d'."
            ),
        )
        pandas_anchor: bool = Field(
            default=False,
            description=(
                "Bucket anchoring. False (default) uses epoch; True uses the "
                "pandas default (origin='start_day')."
            ),
        )
        host: Optional[str] = Field(default=None, description="kdb+ host (default KDB_HOST/localhost).")
        port: Optional[int] = Field(default=None, description="kdb+ port (default KDB_PORT/5000).")
        user: Optional[str] = Field(default=None, description="kdb+ username (default KDB_USER).")
        password: Optional[str] = Field(default=None, description="kdb+ password (default KDB_PASSWORD).")
        start_date: Optional[Union[datetime, dateType]] = Field(
            default=None, description="Start date or datetime (inclusive)."
        )
        end_date: Optional[Union[datetime, dateType]] = Field(
            default=None, description="End date or datetime (inclusive)."
        )

        @field_validator("start_date", "end_date", mode="before")
        @classmethod
        def _coerce_temporal(cls, v):
            # pylint: disable=import-outside-toplevel
            from openbb_kdb.utils import parse_temporal

            return parse_temporal(v)

    _QP.__name__ = f"KDB{label}QueryParams"

    class _Data(data_base):  # type: ignore[valid-type, misc]
        pass

    _Data.__name__ = f"KDB{label}Data"

    class _Fetcher(Fetcher[_QP, List[_Data]]):
        @staticmethod
        # pylint: disable=unused-argument
        def transform_query(params: dict[str, Any]) -> _QP:
            return _QP(**params)

        @staticmethod
        # pylint: disable=unused-argument
        async def aextract_data(query, credentials, **kwargs) -> list[dict]:
            # pylint: disable=import-outside-toplevel
            import asyncio

            return await asyncio.to_thread(_read_sync, query, credentials)

        @staticmethod
        # pylint: disable=unused-argument
        def transform_data(query, data, **kwargs):
            return _validate(query, data, _Data)

    _Fetcher.__name__ = f"KDB{label}Fetcher"
    return _Fetcher


KDBEquityHistoricalFetcher = _build_fetcher(
    "EquityHistorical", EquityHistoricalQueryParams, EquityHistoricalData
)
KDBEtfHistoricalFetcher = _build_fetcher(
    "EtfHistorical", EtfHistoricalQueryParams, EtfHistoricalData
)
KDBCryptoHistoricalFetcher = _build_fetcher(
    "CryptoHistorical", CryptoHistoricalQueryParams, CryptoHistoricalData
)
KDBCurrencyHistoricalFetcher = _build_fetcher(
    "CurrencyHistorical", CurrencyHistoricalQueryParams, CurrencyHistoricalData
)
KDBIndexHistoricalFetcher = _build_fetcher(
    "IndexHistorical", IndexHistoricalQueryParams, IndexHistoricalData
)
