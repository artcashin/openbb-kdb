"""Connection + helpers for the kdb+ integration (PyKX over IPC).

kdb+ is a server process (a `q` instance listening on a port); PyKX connects to
it over IPC. Each OpenBB "symbol" maps to a q table of the same (sanitized) name.
"""

import os
import re
from typing import Any, Optional


# --- connection config -----------------------------------------------------
def resolve_config(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    credentials: Optional[dict] = None,
) -> tuple[str, int, Optional[str], Optional[str]]:
    """Resolve kdb+ connection settings.

    Precedence: explicit arg > OpenBB credential > env var > default.
    Env: KDB_HOST (localhost), KDB_PORT (5000), KDB_USER, KDB_PASSWORD.
    """
    creds = credentials or {}
    host = host or creds.get("kdb_host") or os.getenv("KDB_HOST") or "localhost"
    port = int(port or creds.get("kdb_port") or os.getenv("KDB_PORT") or 5000)
    user = user or creds.get("kdb_user") or os.getenv("KDB_USER") or None
    password = password or creds.get("kdb_password") or os.getenv("KDB_PASSWORD") or None
    return host, port, user, password


def get_connection(
    host: str, port: int, user: Optional[str] = None, password: Optional[str] = None
):
    """Open a synchronous PyKX IPC connection to a kdb+ server."""
    # pylint: disable=import-outside-toplevel
    import pykx as kx

    kwargs: dict[str, Any] = {}
    if user:
        kwargs["username"] = user
    if password:
        kwargs["password"] = password
    return kx.SyncQConnection(host, port, **kwargs)


def table_name(symbol: str) -> str:
    """Sanitize a symbol into a valid q table name (alphanumeric/underscore)."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(symbol).strip())
    if not s or not s[0].isalpha():
        s = "t_" + s
    return s


# --- q operations (kept small + isolated so they can be mocked in tests) ----
def _sym(name: str):
    # pylint: disable=import-outside-toplevel
    import pykx as kx

    return kx.SymbolAtom(name)


def q_set(conn, name: str, df) -> None:
    """`name set table` — (over)write a global q table."""
    # pylint: disable=import-outside-toplevel
    import pykx as kx

    conn("set", _sym(name), kx.toq(df))


def q_get(conn, name: str):
    """`get name` — fetch the q table; returns a PyKX Table."""
    return conn("get", _sym(name))


def q_upsert(conn, name: str, df) -> None:
    """`name upsert table` — append rows to an existing global table."""
    # pylint: disable=import-outside-toplevel
    import pykx as kx

    conn("upsert", _sym(name), kx.toq(df))


def q_tables(conn) -> list[str]:
    """List global tables in the default namespace."""
    return [str(x) for x in conn("tables[`.]").py()]


def q_has(conn, name: str) -> bool:
    """Whether a global table `name` exists."""
    return bool(conn("{x in tables[`.]}", _sym(name)).py())


def q_delete(conn, name: str) -> None:
    """Delete the global table `name` from the default namespace."""
    conn("{![`.;();0b;enlist x]}", _sym(name))


def q_meta(conn, name: str):
    """`meta name` — column types/attributes; returns a pandas DataFrame."""
    return conn("meta", _sym(name)).pd()


# --- temporal helpers (shared shape with the ArcticDB integration) ----------
def parse_temporal(v: Any):
    """str/date/datetime -> date or datetime, preserving the time-of-day."""
    # pylint: disable=import-outside-toplevel
    from datetime import date as dateType, datetime

    if v is None or isinstance(v, datetime):
        return v
    if isinstance(v, dateType):
        return v
    if isinstance(v, str):
        from dateutil import parser

        tail = v.split("T", 1)[1] if "T" in v else ""
        has_time = (":" in v) or any(ch.isdigit() for ch in tail)
        dt = parser.parse(v)
        return dt if has_time else dt.date()
    return v


def to_bounds(start: Any, end: Any):
    """Return (start_ts, end_ts) Timestamps; a pure-date end is end-of-day."""
    # pylint: disable=import-outside-toplevel
    from datetime import date as dateType, datetime

    from pandas import Timedelta, Timestamp

    s = parse_temporal(start)
    e = parse_temporal(end)
    start_ts = None if s is None else Timestamp(s)
    if e is None:
        end_ts = None
    else:
        end_ts = Timestamp(e)
        if isinstance(e, dateType) and not isinstance(e, datetime):
            end_ts = end_ts.normalize() + Timedelta(days=1) - Timedelta(nanoseconds=1)
    return start_ts, end_ts


def normalize_index(df):
    """Coerce a date/datetime column or index into a sorted DatetimeIndex."""
    # pylint: disable=import-outside-toplevel
    from pandas import DatetimeIndex, RangeIndex, to_datetime
    from pandas.api.types import is_numeric_dtype

    if isinstance(df.index, DatetimeIndex):
        return df.sort_index()
    for cand in ("date", "time", "timestamp"):
        if cand in df.columns:
            df = df.set_index(cand)
            df.index.name = "date"
            try:
                df.index = to_datetime(df.index)
                return df.sort_index()
            except (ValueError, TypeError):
                return df
    if not isinstance(df.index, RangeIndex) and not is_numeric_dtype(df.index):
        try:
            df.index = to_datetime(df.index)
            return df.sort_index()
        except (ValueError, TypeError):
            return df
    return df
