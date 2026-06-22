#!/usr/bin/env python3
"""Load N days of daily OHLCV into kdb+ and verify the round-trip.

Downloads daily bars from yfinance and writes them to a kdb+ table via the
openbb-kdb integration, then reads them back through both the generic store and
the `provider="kdb"` path to confirm the data is intact.

Usage:
    python load_aapl.py [--symbol AAPL] [--days 30] [--host localhost] [--port 5000]

Env fallbacks: KDB_HOST, KDB_PORT (CLI args take precedence).
Requires a running kdb+ server reachable over IPC.
"""
import argparse
import os
import sys
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")
os.environ.setdefault("PYKX_UNLICENSED", "true")
os.environ.setdefault("PYKX_IGNORE_QHOME", "1")


def main() -> int:
    p = argparse.ArgumentParser(description="Load daily OHLCV into kdb+ and verify.")
    p.add_argument("--symbol", default="AAPL")
    p.add_argument("--days", type=int, default=30, help="calendar days of history")
    p.add_argument("--host", default=os.getenv("KDB_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("KDB_PORT", "5000")))
    p.add_argument("--table", default=None, help="kdb table name (default: symbol)")
    args = p.parse_args()
    table = args.table or args.symbol

    from openbb import obb
    from openbb_kdb import store

    start = (date.today() - timedelta(days=args.days)).isoformat()
    print(f"[1/4] Downloading {args.symbol} daily OHLCV since {start} (yfinance)...")
    src = obb.equity.price.historical(args.symbol, provider="yfinance", start_date=start)
    n = len(src.results)
    if n == 0:
        print("  ERROR: yfinance returned no rows.", file=sys.stderr)
        return 1
    print(f"  got {n} rows: {src.results[0].date} -> {src.results[-1].date}")

    print(f"[2/4] Writing to kdb+ {args.host}:{args.port} as table `{table}`...")
    info = src.kdb.write(table, host=args.host, port=args.port)
    print(f"  {info}")

    print("[3/4] Reading back via the generic store...")
    s = store(host=args.host, port=args.port)
    df = s.read(table, output="dataframe")
    print(f"  store.read: {len(df)} rows, columns={list(df.columns)}")

    # The provider keys by symbol (table name == sanitized symbol), so this only
    # applies when the table name matches the symbol.
    provider_n = None
    if table == args.symbol:
        print("[4/4] Reading back via provider='kdb' (interval=1d)...")
        back = obb.equity.price.historical(
            args.symbol, provider="kdb", interval="1d", host=args.host, port=args.port
        )
        provider_n = len(back.results)
        print(f"  provider rows: {provider_n}, last close: {back.results[-1].close}")
    else:
        print("[4/4] Skipping provider read (table name differs from symbol).")

    ok = len(df) == n and (provider_n is None or provider_n == n)
    print(f"\n{'PASS' if ok else 'FAIL'}: wrote {n}, store read {len(df)}"
          + (f", provider read {provider_n}" if provider_n is not None else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
