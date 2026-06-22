# openbb-kdb

[kdb+](https://kx.com) integration for the OpenBB Platform, mirroring
`openbb-arcticdb` — **both directions**, via [PyKX](https://github.com/KxSystems/pykx).

Unlike ArcticDB (serverless), **kdb+ is a server process**: PyKX connects to a
running `q` instance over IPC. Each OpenBB symbol maps to a q table of the same
(sanitized) name.

- **Write** — persist any OBBject result to a q table:
  ```python
  res = obb.equity.price.historical("AAPL", provider="yfinance")
  res.kdb.write("AAPL")                 # -> q table `AAPL`
  res.kdb.append("AAPL"); res.kdb.list_symbols(); res.kdb.meta("AAPL"); res.kdb.delete("AAPL")
  ```
- **Read (OHLCV)** — serve stored bars back through OpenBB, for equity / etf /
  crypto / currency / index historical, with **tick→OHLCV resampling**:
  ```python
  obb.equity.price.historical("XYZ", provider="kdb", interval="1m",
                              start_date="2026-06-01", end_date="2026-06-02")
  ```
  Intervals: `1s, 1m/5m/15m/30m, 1h, 1d, 1w/2w, 1mo/3mo` (lowercase `m`=minute).
  `start_date`/`end_date` accept date or datetime. `pandas_anchor` (default
  `False`=epoch) controls bucket anchoring. Resampling is done in pandas (kdb has
  no OpenBB server-side resampler here).
- **Generic store** — arbitrary tables:
  ```python
  from openbb_kdb import store
  s = store(host="localhost", port=5000)
  s.write("trades", my_dataframe); df = s.read("trades", output="dataframe")
  ```

## Connection

No OpenBB credentials and **no secrets are stored in this repository**. Configure
the connection at runtime via environment variables (or per-call params):

| Env var | Default | Notes |
|---|---|---|
| `KDB_HOST` | `localhost` | your kdb+ host |
| `KDB_PORT` | `5000` | your kdb+ port |
| `KDB_USER` | — | optional |
| `KDB_PASSWORD` | — | optional |

Copy `.env.example` to `.env` (git-ignored) and fill in your values, or export
them in your shell. See "Secrets" below.

## Tested against

- **kdb+ 5.0** (build 2026.05.01, `l64arm`) over IPC
- **PyKX 3.1.9** (Python 3.12), unlicensed client mode
- yfinance → kdb+ round-trip verified from both the host and the Docker container
  (`--host host.docker.internal`); see `scripts/load_aapl.py`.

## Requirements & caveats

- Needs a **running kdb+ server** reachable over IPC (PyKX is the client).
- PyKX connects to a remote kdb+ in **unlicensed mode** — **no KX license is
  needed on the client side** (this package). A KX license is only required to run
  embedded/in-process q, which this integration does not use.
- PyKX ships Linux `manylinux_2_17_x86_64` wheels — fine for the amd64 container.
- Date filtering / column selection are applied client-side after fetching the
  table (server-side qSQL push-down is a possible future optimization).

## Secrets

This repo is safe to publish: it contains no host, port, credentials, or license.
- Connection details come from env vars / `.env` (git-ignored), never committed.
- The client needs no KX license; if you place a kdb+ license file in this tree,
  `*.lic` / `kc.lic` / `k4.lic` / `kx.lic` are git-ignored so it can't be pushed.
