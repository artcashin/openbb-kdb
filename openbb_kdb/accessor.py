"""kdb+ OBBject accessor (write path).

Attaches a `.kdb` namespace to every OBBject so any query can be persisted to a
kdb+ table and managed:

    res = obb.equity.price.historical("AAPL", provider="yfinance")
    res.kdb.write("AAPL")              # -> q table `AAPL` on the configured server
    res.kdb.append("AAPL")
    res.kdb.list_symbols(); res.kdb.meta("AAPL"); res.kdb.delete("AAPL")

Connection defaults come from KDB_HOST/KDB_PORT/KDB_USER/KDB_PASSWORD; override
per call with host=/port=/user=/password=. For reading back, see openbb_kdb.store.
"""

from typing import Any, Optional


class KDBAccessor:
    """Persist and manage OBBject results in kdb+."""

    def __init__(self, obbject):
        """Bind the accessor to its OBBject."""
        self._obbject = obbject

    @staticmethod
    def _store(host, port, user, password):
        # pylint: disable=import-outside-toplevel
        from openbb_kdb.store import KDBStore

        return KDBStore(host=host, port=port, user=user, password=password)

    def write(
        self,
        key: str,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict[str, Any]:
        """Write this result to a kdb+ table (overwrites)."""
        return self._store(host, port, user, password).write(key, self._obbject)

    def append(
        self,
        key: str,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict[str, Any]:
        """Append this result to an existing kdb+ table."""
        return self._store(host, port, user, password).append(key, self._obbject)

    def list_symbols(
        self, *, host=None, port=None, user=None, password=None
    ) -> list[str]:
        """List q tables on the server."""
        return self._store(host, port, user, password).list_symbols()

    def meta(self, key: str, *, host=None, port=None, user=None, password=None):
        """Return the q `meta` of the table for `key`."""
        return self._store(host, port, user, password).meta(key)

    def delete(
        self, key: str, *, host=None, port=None, user=None, password=None
    ) -> dict[str, Any]:
        """Delete the q table for `key`."""
        return self._store(host, port, user, password).delete(key)
