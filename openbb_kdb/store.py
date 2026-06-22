"""Generic read/write API for arbitrary data in a kdb+ database (via PyKX).

Each key maps to a q table (named after the sanitized key). Mirrors the ArcticDB
store: handles OBBjects, DataFrames, or records, and returns an OBBject or a
DataFrame on read.

    from openbb_kdb import store
    s = store(host="localhost", port=5000)
    s.write("AAPL", obb.equity.price.historical("AAPL", provider="yfinance"))
    df  = s.read("AAPL", output="dataframe", start_date="2026-01-01")
    obj = s.read("AAPL")
    s.list_symbols(); s.has("AAPL"); s.meta("AAPL"); s.delete("AAPL"); s.append("AAPL", more)
"""

from typing import Any, Optional, Sequence


class KDBStore:
    """Generic kdb+ store for arbitrary tabular data."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        conn: Any = None,
    ):
        """Resolve connection settings; an explicit `conn` (e.g. for tests) wins."""
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import resolve_config

        self.host, self.port, self.user, self.password = resolve_config(
            host, port, user, password, None
        )
        self._conn_obj = conn

    def _conn(self):
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import get_connection

        if self._conn_obj is None:
            self._conn_obj = get_connection(
                self.host, self.port, self.user, self.password
            )
        return self._conn_obj

    @staticmethod
    def _to_frame(data: Any):
        """OBBject / DataFrame / records -> a column-oriented frame for kdb.

        kdb tables are column-based, so any datetime index is reset into a `date`
        column rather than kept as an index.
        """
        # pylint: disable=import-outside-toplevel
        from pandas import DataFrame, DatetimeIndex

        from openbb_kdb.utils import normalize_index

        if hasattr(data, "to_dataframe"):  # OBBject
            df = data.to_dataframe()
        elif isinstance(data, DataFrame):
            df = data.copy()
        else:
            df = DataFrame(data)
        if df is None or df.empty:
            raise ValueError("No data to write to kdb+.")
        df = normalize_index(df)
        if isinstance(df.index, DatetimeIndex):
            df = df.reset_index()  # date becomes a column
        return df

    @staticmethod
    def _to_obbject(df, key: Optional[str]):
        # pylint: disable=import-outside-toplevel
        from pandas import RangeIndex

        from openbb_core.app.model.obbject import OBBject
        from openbb_core.provider.abstract.data import Data

        out = df.reset_index(drop=isinstance(df.index, RangeIndex))
        results = [
            Data.model_validate(
                {k: v for k, v in rec.items() if not (isinstance(v, float) and v != v)}
            )
            for rec in out.to_dict("records")
        ]
        return OBBject(results=results, provider="kdb", extra={"symbol": key})

    # -- write --------------------------------------------------------------
    def write(self, key: str, data: Any) -> dict[str, Any]:
        """Write data to a q table named after `key` (overwrites)."""
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import q_set, table_name

        df = self._to_frame(data)
        name = table_name(key)
        q_set(self._conn(), name, df)
        return {"host": self.host, "port": self.port, "table": name,
                "symbol": key, "rows": int(len(df))}

    def append(self, key: str, data: Any) -> dict[str, Any]:
        """Append rows to an existing q table (schema must match)."""
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import q_upsert, table_name

        df = self._to_frame(data)
        name = table_name(key)
        q_upsert(self._conn(), name, df)
        return {"host": self.host, "port": self.port, "table": name,
                "symbol": key, "rows_appended": int(len(df))}

    # -- read ---------------------------------------------------------------
    def read(
        self,
        key: str,
        *,
        start_date: Any = None,
        end_date: Any = None,
        columns: Optional[Sequence[str]] = None,
        output: str = "obbject",
    ):
        """Read a q table; returns an OBBject (default) or DataFrame.

        Date filtering / column selection are applied client-side after fetching
        the table. `start_date`/`end_date` accept date, datetime, or string.
        """
        # pylint: disable=import-outside-toplevel
        from pandas import DatetimeIndex

        from openbb_kdb.utils import normalize_index, q_get, q_has, table_name, to_bounds

        conn = self._conn()
        name = table_name(key)
        if not q_has(conn, name):
            raise FileNotFoundError(
                f"kdb+ table '{name}' not found on {self.host}:{self.port}."
            )
        df = q_get(conn, name).pd()
        df = normalize_index(df)
        start_ts, end_ts = to_bounds(start_date, end_date)
        if isinstance(df.index, DatetimeIndex) and (start_ts is not None or end_ts is not None):
            lo = start_ts if start_ts is not None else df.index.min()
            hi = end_ts if end_ts is not None else df.index.max()
            df = df.loc[lo:hi]
        if columns:
            df = df[[c for c in columns if c in df.columns]]
        if output == "dataframe":
            return df
        return self._to_obbject(df, key)

    # -- catalog ------------------------------------------------------------
    def list_symbols(self) -> list[str]:
        """List q tables in the default namespace."""
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import q_tables

        return q_tables(self._conn())

    def has(self, key: str) -> bool:
        """Whether a table for `key` exists."""
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import q_has, table_name

        return q_has(self._conn(), table_name(key))

    def delete(self, key: str) -> dict[str, Any]:
        """Delete the q table for `key`."""
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import q_delete, table_name

        name = table_name(key)
        q_delete(self._conn(), name)
        return {"host": self.host, "port": self.port, "deleted": name}

    def meta(self, key: str):
        """Return the q `meta` (column types/attributes) of the table."""
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.utils import q_meta, table_name

        return q_meta(self._conn(), table_name(key))


def store(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    conn: Any = None,
) -> KDBStore:
    """Convenience factory: `store(host="localhost", port=5000)`."""
    return KDBStore(host=host, port=port, user=user, password=password, conn=conn)
