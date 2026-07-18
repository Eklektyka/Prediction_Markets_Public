"""
pm_gapfill.py — Gap-fill Polymarket UFC/MMA trades Apr 1 2026 → today.
Resume-safe checkpointing; polite rate-limiting; runs unattended.

═══════════════════════════════════════════════════════════════════════
API → INTERNAL SCHEMA FIELD MAPPING
═══════════════════════════════════════════════════════════════════════
Source: data-api.polymarket.com/trades  (public, no auth)
This is the activity-feed API — distinct from on-chain Lychee format
(Lychee indexes CTF ERC-1155 transfers on Polygon mainnet; this API
exposes the same fills from the taker's perspective).

data-api field    | Type          | Internal field   | Notes
------------------|---------------|------------------|----------------------------------
timestamp         | int (unix s)  | timestamp        | UTC; converted to ns
price             | float (0–1)   | price_yes        | YES outcome probability
                  |               |                  | If outcome=="No": price_yes = 1-p
asset             | str (decimal) | token_id         | YES or NO outcome token
conditionId       | str (hex)     | condition_id     | Polymarket condition ID
side              | "BUY"/"SELL"  | taker_side       | Taker's perspective
size              | float (shares)| size             | Shares traded
outcome           | "Yes"/"No"    | outcome          | Which outcome token was traded
transactionHash   | str (hex)     | tx_hash          | Polygon tx (for dedup)
title             | str           | question         | Market question text
slug              | str           | market_slug      | Market slug (fight ID proxy)

Derived:
  usdc_amount = size * price_yes_raw  (USDC notional, NOT price_yes-adjusted)

Key differences from Lychee on-chain format:
  - Lychee: binary maker/taker roles encoded as ERC-1155 asset transfers
    (maker_asset_id="0" means maker paid USDC; taker_asset_id=token)
  - data-api: unified taker-view; side=BUY → taker bought outcome token
  - data-api price is the traded price for the outcome token (0–1)
  - Lychee price_yes was reconstructed from USDC/token amount ratio
  - data-api includes NO-token trades; we flip price_yes = 1 - price
    for those rows so all rows are expressed on the YES scale
═══════════════════════════════════════════════════════════════════════
"""

import sys, json, time, math, os, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────
ROOT        = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
RAW_DIR     = ROOT / "data/raw/pm_gapfill"
CKPT_DIR    = RAW_DIR / "checkpoints"
INTERIM_DIR = ROOT / "data/interim"
OUT_PARQUET = INTERIM_DIR / "pm_gapfill_trades.parquet"
MARKETS_OUT = RAW_DIR / "markets_discovered.json"

for d in (RAW_DIR, CKPT_DIR, INTERIM_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────
GAMMA_BASE   = "https://gamma-api.polymarket.com"
DATA_API     = "https://data-api.polymarket.com"

# Discover markets created since DISC_SINCE (to catch late-March events with April fights)
DISC_SINCE   = "2026-03-01"
# Only pull trades on or after START_TS (avoid duplicating Lychee data)
START_TS     = int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp())  # 1743465600
TODAY_STR    = datetime.now(timezone.utc).strftime("%Y-%m-%d")

PAGE_EVENTS  = 50    # events per gamma page
PAGE_TRADES  = 500   # trades per data-api page
SLEEP_OK     = 0.20  # polite delay between requests (s)
SLEEP_RETRY  = 2.0   # base backoff (s)
MAX_RETRIES  = 5
MAX_PAGES    = 50    # safety cap per market (50 × 500 = 25,000 trades max)

# UFC/MMA event tags to query
UFC_TAGS     = ("ufc", "mma")
# Dated fight event: event slug ends with YYYY-MM-DD
DATED_FIGHT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")

SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-gapfill-research/1.0"})


# ── Utilities ──────────────────────────────────────────────────────────

def get_json(url, params=None, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            r = SESS.get(url, params=params, timeout=30)
            if r.status_code == 429:
                wait = SLEEP_RETRY * (2 ** attempt)
                print(f"    429 rate-limit — sleeping {wait:.0f}s …", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"    FAILED {url}: {e}", flush=True)
                return None
            time.sleep(SLEEP_RETRY * (2 ** attempt))
    return None


def ckpt_path(cid: str) -> Path:
    return CKPT_DIR / f"{cid[:20]}.json"

def load_ckpt(cid: str) -> dict:
    p = ckpt_path(cid)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"done": False}

def save_ckpt(cid: str, state: dict):
    ckpt_path(cid).write_text(json.dumps(state))

def jsonl_path(cid: str) -> Path:
    return RAW_DIR / f"{cid[:20]}_trades.jsonl"


# ── Market discovery ───────────────────────────────────────────────────

def discover_markets() -> list[dict]:
    """
    Pull all UFC/MMA events from Gamma API created >= DISC_SINCE.
    Returns a flat list of market dicts (one per conditionId) with:
      conditionId, clobTokenIds, slug, question, event_slug, created_at
    """
    seen_cids = {}

    for tag in UFC_TAGS:
        offset = 0
        stop   = False
        while not stop:
            params = {
                "tag_slug":  tag,
                "limit":     PAGE_EVENTS,
                "order":     "createdAt",
                "ascending": "false",
                "offset":    offset,
            }
            data = get_json(f"{GAMMA_BASE}/events", params=params)
            time.sleep(SLEEP_OK)
            if not data:
                break

            events = data if isinstance(data, list) else data.get("data", [])
            if not events:
                break

            for ev in events:
                created = (ev.get("createdAt") or ev.get("creationDate") or "")[:10]
                if created and created < DISC_SINCE:
                    stop = True   # Events are newest-first; once past cutoff, done
                    break

                ev_slug = ev.get("slug", "")
                for mkt in ev.get("markets", []):
                    cid = mkt.get("conditionId", "")
                    if not cid or cid in seen_cids:
                        continue
                    # Parse clobTokenIds (may be JSON string or list)
                    tok_raw = mkt.get("clobTokenIds", [])
                    if isinstance(tok_raw, str):
                        try:
                            tok_raw = json.loads(tok_raw)
                        except Exception:
                            tok_raw = []
                    seen_cids[cid] = {
                        "condition_id": cid,
                        "token_ids":    tok_raw,
                        "slug":         mkt.get("slug", ""),
                        "question":     mkt.get("question", ""),
                        "event_slug":   ev_slug,
                        "created_at":   created,
                    }

            if len(events) < PAGE_EVENTS:
                break
            # Stop if oldest event on page pre-dates our window
            oldest = min((e.get("createdAt") or "")[:10] for e in events)
            if oldest and oldest < DISC_SINCE:
                break
            offset += PAGE_EVENTS

        print(f"  tag={tag!r}: {len(seen_cids)} markets so far", flush=True)

    markets = list(seen_cids.values())
    print(f"  Total unique markets discovered: {len(markets)}", flush=True)
    return markets


# ── Trade collection ───────────────────────────────────────────────────

def fetch_market_trades(mkt: dict) -> list[dict]:
    """
    Fetch all trades for mkt from data-api using market= param (correct filter).
    Paginate newest-first, stopping when oldest trade < START_TS.
    Append to per-market JSONL. Returns raw trade list.
    """
    cid  = mkt["condition_id"]
    ckpt = load_ckpt(cid)

    if ckpt.get("done"):
        # Load existing raw trades from JSONL
        jl = jsonl_path(cid)
        if jl.exists():
            raw = []
            for line in jl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        raw.append(json.loads(line))
                    except Exception:
                        pass
            return raw
        return []

    # Not done: (re)fetch all pages. Truncate stale JSONL first.
    jl = jsonl_path(cid)
    jl.write_text("", encoding="utf-8")  # start fresh

    all_raw = []
    offset  = 0
    n_pages = 0

    while n_pages < MAX_PAGES:
        # IMPORTANT: use 'market' param, NOT 'conditionId'
        # data-api.polymarket.com/trades?market=<conditionId> filters correctly;
        # ?conditionId=... is silently ignored and returns the unfiltered global feed.
        params = {"market": cid, "limit": PAGE_TRADES, "offset": offset}
        resp   = get_json(f"{DATA_API}/trades", params=params)
        time.sleep(SLEEP_OK)
        n_pages += 1

        if not resp:
            break

        page = resp if isinstance(resp, list) else []
        if not page:
            break

        # Append raw to JSONL
        with open(jl, "a", encoding="utf-8") as f:
            for t in page:
                f.write(json.dumps(t) + "\n")

        all_raw.extend(page)

        if len(page) < PAGE_TRADES:
            break  # Last page

        # Oldest on this page — API returns newest-first
        oldest_ts = min(t.get("timestamp", 9e18) for t in page)
        if oldest_ts < START_TS:
            break  # Went past our start date

        offset += PAGE_TRADES

    save_ckpt(cid, {"done": True, "n_raw": len(all_raw)})
    return all_raw


# ── Normalization ──────────────────────────────────────────────────────

def normalize_trade(raw: dict, mkt: dict) -> dict | None:
    """
    Map a data-api trade record to internal schema.
    Returns None if trade is outside [START_TS, ∞).
    """
    ts = raw.get("timestamp", 0)
    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return None

    if ts_int < START_TS:
        return None

    price_raw = raw.get("price", 0)
    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        price = float("nan")

    outcome = raw.get("outcome", "Yes")
    price_yes = price if outcome != "No" else (1.0 - price)

    size_raw = raw.get("size", 0)
    try:
        size = float(size_raw)
    except (TypeError, ValueError):
        size = float("nan")

    # USDC notional uses the raw traded price (not the YES-flipped one)
    usdc_amount = size * price if not (math.isnan(size) or math.isnan(price)) else float("nan")

    return {
        "timestamp":    pd.Timestamp(ts_int * 1_000_000_000, unit="ns", tz="UTC"),
        "price_yes":    round(price_yes, 8),
        "price_raw":    round(price, 8),
        "size":         round(size, 8),
        "usdc_amount":  round(usdc_amount, 8),
        "outcome":      outcome,
        "taker_side":   raw.get("side", ""),
        "condition_id": raw.get("conditionId", mkt["condition_id"]),
        "token_id":     raw.get("asset", ""),
        "market_slug":  raw.get("slug",  mkt.get("slug", "")),
        "event_slug":   mkt.get("event_slug", ""),
        "question":     raw.get("title", mkt.get("question", "")),
        "tx_hash":      raw.get("transactionHash", ""),
        "proxy_wallet": raw.get("proxyWallet", ""),
    }


# ── Main ───────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(f"pm_gapfill — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Gap window:  {datetime.fromtimestamp(START_TS, tz=timezone.utc).strftime('%Y-%m-%d')} -> {TODAY_STR}")
    print(f"Disc since:  {DISC_SINCE}")
    print()

    # ── Step 1: load or discover markets ───────────────────────────────
    print("=" * 60)
    print("Step 1: Markets")
    print("=" * 60)

    if MARKETS_OUT.exists():
        all_markets = json.loads(MARKETS_OUT.read_text(encoding="utf-8"))
        print(f"  Loaded existing markets_discovered.json ({len(all_markets)} total)")
        # Filter to dated fight events only (excludes 'who will X fight next' props)
        markets = [m for m in all_markets if DATED_FIGHT_RE.search(m.get("event_slug", ""))]
        print(f"  After dated-fight filter: {len(markets)} markets")
        n_evs = len(set(m["event_slug"] for m in markets))
        print(f"  Across {n_evs} fight events")
    else:
        print("  Discovering markets via Gamma API …")
        all_markets = discover_markets()
        MARKETS_OUT.write_text(json.dumps(all_markets, indent=2, default=str), encoding="utf-8")
        markets = [m for m in all_markets if DATED_FIGHT_RE.search(m.get("event_slug", ""))]
        print(f"  Saved {len(all_markets)} total, {len(markets)} after dated-fight filter")
    print()

    if not markets:
        print("No markets found — check API or date filter.")
        return

    # ── Wipe bad checkpoints from any prior buggy run ───────────────────
    # Previous run used ?conditionId= (wrong param; returns global feed).
    # Detect by checking if any JSONL has conditionId mismatch on first line.
    stale = []
    for p in CKPT_DIR.iterdir():
        cid_prefix = p.stem  # first 20 chars of conditionId
        jl = RAW_DIR / f"{cid_prefix}_trades.jsonl"
        if jl.exists():
            first = ""
            try:
                first = jl.read_text(encoding="utf-8").splitlines()[0]
                t0rec = json.loads(first)
                actual_cid = t0rec.get("conditionId", "")
                # Bad if the conditionId in the record doesn't match the file's market
                mkt_match = next(
                    (m for m in markets if m["condition_id"][:20] == cid_prefix), None
                )
                if mkt_match and actual_cid != mkt_match["condition_id"]:
                    stale.append((p, jl))
            except Exception:
                stale.append((p, jl))
    if stale:
        print(f"  Wiping {len(stale)} stale checkpoints from prior bad run …")
        for p, jl in stale:
            p.unlink(missing_ok=True)
            jl.unlink(missing_ok=True)
        print(f"  Done. Fresh run will re-fetch those markets.")
    print()

    # ── Step 2: pull trades ─────────────────────────────────────────────
    print("=" * 60)
    print(f"Step 2: Pull trades ({len(markets)} markets)")
    print("=" * 60)

    all_norm   = []
    n_with     = 0
    n_empty    = 0
    n_resumed  = 0

    for i, mkt in enumerate(markets, 1):
        cid  = mkt["condition_id"]
        slug = mkt.get("slug", cid[:16])

        was_done = load_ckpt(cid).get("done", False)
        raw_list = fetch_market_trades(mkt)
        if was_done:
            n_resumed += 1

        # Normalize
        norm = [normalize_trade(t, mkt) for t in raw_list]
        norm = [t for t in norm if t is not None]

        if norm:
            all_norm.extend(norm)
            n_with += 1
        else:
            n_empty += 1

        if i % 25 == 0 or i == len(markets):
            elapsed = time.time() - t0
            print(
                f"  [{i:>4}/{len(markets)}] {elapsed:>5.0f}s | "
                f"trades: {len(all_norm):>7,} | "
                f"w/data: {n_with} | empty: {n_empty} | resumed: {n_resumed}",
                flush=True,
            )
        elif norm:
            print(f"  [{i:>4}/{len(markets)}] {slug}: {len(norm):>4} trades", flush=True)

    print()

    # ── Step 3: assemble parquet ────────────────────────────────────────
    print("=" * 60)
    print("Step 3: Write output parquet")
    print("=" * 60)

    if not all_norm:
        print("  No trades collected.")
        return

    df = pd.DataFrame(all_norm)

    # Deduplicate by (tx_hash, token_id) — handles any JSONL overlap
    before = len(df)
    df = df.drop_duplicates(subset=["tx_hash", "token_id"]).reset_index(drop=True)
    print(f"  Dedup: {before:,} → {len(df):,} rows")

    # Sort by time
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Sanity: drop rows with price_yes outside (0,1]
    bad = (~df["price_yes"].between(0.0, 1.0, inclusive="both"))
    if bad.any():
        print(f"  Dropping {bad.sum()} rows with price_yes outside [0,1]")
        df = df[~bad].reset_index(drop=True)

    df.to_parquet(OUT_PARQUET, index=False)
    print(f"  Written: {OUT_PARQUET}")

    # ── Summary ─────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Markets discovered:  {len(markets)}")
    print(f"  Markets with trades: {n_with}")
    print(f"  Markets empty:       {n_empty}")
    print(f"  Trades pulled:       {len(df):,}")
    ts_min = df["timestamp"].min()
    ts_max = df["timestamp"].max()
    print(f"  Date range:          {ts_min.strftime('%Y-%m-%d')} → {ts_max.strftime('%Y-%m-%d')}")
    print(f"  Elapsed:             {elapsed:.0f}s")
    print()

    # Market breakdown
    by_ev = df.groupby("event_slug").agg(
        markets=("condition_id", "nunique"),
        trades=("tx_hash", "count"),
    ).sort_values("trades", ascending=False)
    print("Top 15 events by trade count:")
    print(by_ev.head(15).to_string())


if __name__ == "__main__":
    main()
