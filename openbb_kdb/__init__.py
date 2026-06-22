"""kdb+ integration for OpenBB (provider + OBBject accessor + generic store)."""

from openbb_core.app.model.extension import Extension
from openbb_core.provider.abstract.provider import Provider

from openbb_kdb.accessor import KDBAccessor
from openbb_kdb.models.historical import (
    KDBCryptoHistoricalFetcher,
    KDBCurrencyHistoricalFetcher,
    KDBEquityHistoricalFetcher,
    KDBEtfHistoricalFetcher,
    KDBIndexHistoricalFetcher,
)
from openbb_kdb.store import KDBStore, store

__all__ = ["kdb_provider", "ext", "KDBStore", "store"]

# --- Read path: provider extension -----------------------------------------
kdb_provider = Provider(
    name="kdb",
    website="https://kx.com",
    description=(
        "Serve bars stored in a kdb+ table through the standard OpenBB interface "
        "(equity/etf/crypto/currency/index historical), with tick->OHLCV "
        "resampling. Connects to a kdb+ server over IPC via PyKX. Pair with the "
        "`.kdb` OBBject accessor and the openbb_kdb.store API to persist/read data."
    ),
    # No credentials: connection is configured via KDB_HOST/KDB_PORT/KDB_USER/
    # KDB_PASSWORD env vars or per-call query params (declaring credentials would
    # make them mandatory).
    credentials=None,
    fetcher_dict={
        "EquityHistorical": KDBEquityHistoricalFetcher,
        "EtfHistorical": KDBEtfHistoricalFetcher,
        "CryptoHistorical": KDBCryptoHistoricalFetcher,
        "CurrencyHistorical": KDBCurrencyHistoricalFetcher,
        "IndexHistorical": KDBIndexHistoricalFetcher,
    },
    repr_name="kdb+",
)

# --- Write path: OBBject accessor ------------------------------------------
ext = Extension(name="kdb", description="Persist OBBject results to a kdb+ table.")
KDB = ext.obbject_accessor(KDBAccessor)
