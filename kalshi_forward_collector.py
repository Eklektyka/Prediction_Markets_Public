#!/usr/bin/env python3
"""
kalshi_forward_collector.py  —  Phase 0.4 forward collector (v2, memory-safe).

WHY v2: v1 accumulated every trade in RAM before writing, and the exchange firehose
is 30M+ trades over the ~100-day live window -> MemoryError. v2 fixes this two ways:
  1. STREAM TO DISK: every page (<=1000 trades) is written to Parquet immediately and
     then discarded. Memory stays flat no matter how much history you pull.
  2. SERVER-SIDE FILTERING for backfill: instead of downloading the whole firehose and
     filtering locally, it asks Kalshi for the markets under each of YOUR series, then
     pulls trades per market. Targeted and small.

Two jobs:
  BACKFILL (run once, targeted):
      python kalshi_forward_collector.py --backfill
    For each series in SERIES (below), lists that series' markets, then pages their
    trades to disk. This is what you run today to seed history for your research series.

  INCREMENTAL (run on a schedule, e.g. every 12 min):
      python kalshi_forward_collector.py
    Pulls only trades since the last run (via min_ts checkpoint) across the firehose,
    keeps the ones matching SERIES, writes per page. Volume per run is tiny (minutes of
    trades), so no memory issue. On a COLD start with no saved state it only looks back
    INCREMENTAL_COLD_HOURS (default 24h) -- it will NOT accidentally pull 100 days.

Verified vs docs.kalshi.com (July 2026): host external-api.kalshi.com; trades at
/trade-api/v2/markets/trades (params ticker,limit<=1000,cursor,min_ts,max_ts); markets
at /trade-api/v2/markets (filter series_ticker, status); RSA-PSS auth, salt=DIGEST_LENGTH;
trades carry taker_side. NOTE: markets/trades serves the LIVE tier (~100 days). Markets
that settled before the historical cutoff need the /historical/trades endpoint (not wired
here yet) -- fine for current research series, flag if you need older history.

Credentials (env.env in repo root): KALSHI_KEYID + KALSHI_KEYFILE=key.txt
Series to collect (env override): SERIES="KXUFC,KXFED,KXCPIYOY,..."   comma-separated.
"""
from __future__ import annotations
import os, sys, json, time, base64, logging, datetime as dt
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# ------------------------------------------------------------------ config ----
BASE_URL    = os.getenv("KALSHI_BASE_URL", "https://external-api.kalshi.com")
TRADES_PATH = "/trade-api/v2/markets/trades"
MARKETS_PATH = "/trade-api/v2/markets"
PAGE_LIMIT  = 1000
CADENCE_OVERLAP_S = 120
INCREMENTAL_COLD_HOURS = int(os.getenv("INCREMENTAL_COLD_HOURS", "24"))

# Your research series (series tickers). Backfill iterates these; incremental keeps these.
DEFAULT_SERIES = "KXUFC,KXFED,KXFEDDECISION,KXCPIYOY,KXCPICOREYOY,KXPAYROLLS,KXU3"
SERIES = tuple(s.strip() for s in os.getenv("SERIES", DEFAULT_SERIES).split(",") if s.strip())

ROOT       = Path(os.getenv("COLLECTOR_ROOT", "."))
RAW_DIR    = ROOT / "data" / "raw" / "live"
META_DIR   = ROOT / "data" / "meta"
QA_DIR     = ROOT / "qa"
STATE_FILE = META_DIR / "collector_state.json"
FAIL_LOG   = QA_DIR / "collector_failures.log"
for d in (RAW_DIR, META_DIR, QA_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(FAIL_LOG, mode="a")],
)
log = logging.getLogger("kalshi_collector")

# --------------------------------------------------------------- auth client --
def load_private_key() -> rsa.RSAPrivateKey:
    if Path("env.env").exists():
        load_dotenv("env.env")
    keyfile = os.getenv("KALSHI_KEYFILE")
    pem = os.getenv("KALSHI_PRIVATE_KEY")
    if keyfile and Path(keyfile).exists():
        data = Path(keyfile).read_bytes()
    elif pem:
        data = pem.encode()
    else:
        raise SystemExit("No key. Set KALSHI_KEYFILE=key.txt (or KALSHI_PRIVATE_KEY) in env.env.")
    return serialization.load_pem_private_key(data, password=None)

class Kalshi:
    def __init__(self, key_id: str, pk: rsa.RSAPrivateKey):
        self.key_id, self.pk, self.s = key_id, pk, requests.Session()

    def _headers(self, method: str, path: str) -> dict:
        ts = str(int(time.time() * 1000))
        sig = self.pk.sign((ts + method + path.split("?")[0]).encode(),
                           padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                       salt_length=padding.PSS.DIGEST_LENGTH),
                           hashes.SHA256())
        return {"KALSHI-ACCESS-KEY": self.key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
                "Content-Type": "application/json"}

    def get(self, path: str, **params) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        for attempt in range(6):
            r = self.s.get(BASE_URL + path, headers=self._headers("GET", path),
                           params=params, timeout=30)
            if r.status_code == 429:
                wait = 2 ** attempt; log.warning("429; backing off %ss", wait); time.sleep(wait); continue
            r.raise_for_status(); return r.json()
        raise RuntimeError("repeated 429s")

# --------------------------------------------------------------- disk writer --
def write_page(df: pd.DataFrame, tag: str) -> None:
    """Write ONE page to raw/live/date=.../trades_<tag>.parquet, partitioned by trade date."""
    if df.empty:
        return
    df = df.copy()
    df["created_time"] = pd.to_datetime(df["created_time"], utc=True, format="ISO8601")   # tz-aware UTC once
    for day, chunk in df.groupby(df["created_time"].dt.date):
        part = RAW_DIR / f"date={day.isoformat()}"; part.mkdir(parents=True, exist_ok=True)
        out = part / f"trades_{tag}_{int(time.time()*1000)}_{len(chunk)}.parquet"
        chunk.to_parquet(out, index=False)

# --------------------------------------------------------------- state I/O ----
def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"last_max_ts": None}
def save_state(st: dict) -> None:
    STATE_FILE.write_text(json.dumps(st, indent=2))

# --------------------------------------------------------------- BACKFILL -----
def list_market_tickers(client: Kalshi, series: str) -> list[str]:
    """All market tickers under a series (all statuses), paginated."""
    tickers, cursor = [], None
    while True:
        page = client.get(MARKETS_PATH, series_ticker=series, limit=1000, cursor=cursor)
        for m in page.get("markets", []):
            if m.get("ticker"):
                tickers.append(m["ticker"])
        cursor = page.get("cursor")
        if not cursor:
            break
        time.sleep(0.1)
    return tickers

def backfill_ticker(client: Kalshi, ticker: str) -> int:
    """Page a single market's trades to disk, discarding each page after write."""
    cursor, n, pg = None, 0, 0
    while True:
        page = client.get(TRADES_PATH, ticker=ticker, limit=PAGE_LIMIT, cursor=cursor)
        batch = page.get("trades", [])
        if batch:
            write_page(pd.DataFrame(batch), tag=ticker.replace("/", "_"))
            n += len(batch)
        pg += 1
        cursor = page.get("cursor")
        if not cursor or not batch:
            break
        time.sleep(0.1)
    if n:
        log.info("  %s: %d trades (%d pages)", ticker, n, pg)
    return n

def run_backfill(client: Kalshi) -> None:
    grand = 0
    for series in SERIES:
        log.info("series %s: listing markets...", series)
        try:
            tickers = list_market_tickers(client, series)
        except Exception as e:
            log.exception("could not list markets for %s: %s", series, e); continue
        log.info("series %s: %d markets", series, len(tickers))
        for i, t in enumerate(tickers, 1):
            try:
                grand += backfill_ticker(client, t)
            except Exception as e:
                log.exception("  %s failed: %s", t, e)
            if i % 25 == 0:
                log.info("  ...%d/%d markets done in %s", i, len(tickers), series)
    log.info("BACKFILL done: %d trades across %d series", grand, len(SERIES))

# --------------------------------------------------------------- INCREMENTAL --
def keep(row: dict) -> bool:
    t = row.get("ticker", "")
    return any(t.startswith(p) for p in SERIES)

def run_incremental(client: Kalshi) -> None:
    st = load_state()
    last = st.get("last_max_ts")
    if last is None:
        min_ts = int(time.time()) - INCREMENTAL_COLD_HOURS * 3600
        log.info("cold start: looking back %dh (min_ts=%d)", INCREMENTAL_COLD_HOURS, min_ts)
    else:
        min_ts = max(0, last - CADENCE_OVERLAP_S)
    cursor, kept, newest, pg = None, 0, last or 0, 0
    while True:
        page = client.get(TRADES_PATH, limit=PAGE_LIMIT, cursor=cursor, min_ts=min_ts)
        batch = page.get("trades", [])
        mine = [r for r in batch if keep(r)]
        if mine:
            df = pd.DataFrame(mine)
            write_page(df, tag="inc")
            kept += len(mine)
            newest = max(newest, int(pd.to_datetime(df["created_time"], utc=True, format="ISO8601").max().timestamp()))
        pg += 1
        cursor = page.get("cursor")
        if not cursor or not batch:
            break
        time.sleep(0.1)
    if newest:
        st["last_max_ts"] = newest; save_state(st)
    log.info("incremental done: %d matching trades kept (%d pages scanned)", kept, pg)

# --------------------------------------------------------------- main ---------
def main(backfill: bool) -> None:
    if Path("env.env").exists():
        load_dotenv("env.env")
    key_id = os.getenv("KALSHI_KEYID")
    if not key_id:
        raise SystemExit("KALSHI_KEYID not set in env.env.")
    client = Kalshi(key_id, load_private_key())
    log.info("series: %s", ", ".join(SERIES))
    try:
        run_backfill(client) if backfill else run_incremental(client)
    except Exception as e:
        log.exception("run failed: %s", e); sys.exit(1)

if __name__ == "__main__":
    main(backfill="--backfill" in sys.argv)
