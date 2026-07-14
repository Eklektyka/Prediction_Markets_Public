"""
STATUS: NOT YET RUN — output has NOT been merged into pm_gapfill_trades.parquet.
This script would extend gap-fill coverage backward to 2026-02-01 (Feb–Mar 2026 fights,
primarily Perez/Chiasson 2026-02-28). Run only when ready to extend 2026 coverage;
use pm_gapfill.py for Apr-Jul 2026 (already complete).

pm_gapfill_ext.py — Extend PM gap-fill backward to 2026-02-01.

Discovers UFC/MMA events created since 2026-01-01 whose end_date falls
in [2026-02-01, 2026-04-01).  Fetches all trades for those markets.
Appends (with dedup on tx_hash+token_id) to pm_gapfill_trades.parquet.

Uses separate checkpoint prefix "ext_" so existing Apr-Jul checkpoints
are untouched.  Safe to re-run.

Expected runtime: ~10-30 min depending on number of markets discovered.
"""

import sys, json, time, math, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests, pandas as pd, numpy as np
from pathlib import Path
from datetime import datetime, timezone

ROOT        = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
RAW_DIR     = ROOT / "data/raw/pm_gapfill"
CKPT_DIR    = RAW_DIR / "checkpoints_ext"   # separate from main checkpoints
INTERIM_DIR = ROOT / "data/interim"
OUT_PARQUET = INTERIM_DIR / "pm_gapfill_trades.parquet"

for d in (RAW_DIR, CKPT_DIR):
    d.mkdir(parents=True, exist_ok=True)

GAMMA_BASE  = "https://gamma-api.polymarket.com"
DATA_API    = "https://data-api.polymarket.com"

DISC_SINCE  = "2026-01-01"
WIN_START   = int(datetime(2026, 2,  1, tzinfo=timezone.utc).timestamp())
WIN_END     = int(datetime(2026, 4,  1, tzinfo=timezone.utc).timestamp())

PAGE_EVENTS = 50
PAGE_TRADES = 500
SLEEP_OK    = 0.25
SLEEP_RETRY = 2.0
MAX_RETRIES = 5
MAX_PAGES   = 100

UFC_TAGS    = ("ufc", "mma")
DATED_RE    = re.compile(r"-\d{4}-\d{2}-\d{2}$")

SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-gapfill-ext-research/1.0"})


def get_json(url, params=None):
    for attempt in range(MAX_RETRIES):
        try:
            r = SESS.get(url, params=params, timeout=30)
            if r.status_code == 429:
                wait = SLEEP_RETRY * (2 ** attempt)
                print(f"    429 — sleeping {wait:.0f}s", flush=True)
                time.sleep(wait); continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                print(f"    FAILED {url}: {e}", flush=True)
                return None
            time.sleep(SLEEP_RETRY * (2 ** attempt))
    return None


def ckpt_path(cid): return CKPT_DIR / f"{cid[:20]}.json"
def load_ckpt(cid):
    p = ckpt_path(cid)
    if p.exists():
        try: return json.loads(p.read_text())
        except: pass
    return {"done": False}
def save_ckpt(cid, state): ckpt_path(cid).write_text(json.dumps(state))

def jsonl_path(cid): return RAW_DIR / f"ext_{cid[:20]}_trades.jsonl"


def discover_markets():
    """Return UFC/MMA markets whose end_date is in [WIN_START, WIN_END)."""
    seen = {}
    win_start_dt = datetime.fromtimestamp(WIN_START, tz=timezone.utc).date()
    win_end_dt   = datetime.fromtimestamp(WIN_END,   tz=timezone.utc).date()

    for tag in UFC_TAGS:
        offset = 0
        stop   = False
        while not stop:
            params = {"tag_slug": tag, "limit": PAGE_EVENTS,
                      "order": "createdAt", "ascending": "false", "offset": offset}
            data = get_json(f"{GAMMA_BASE}/events", params=params)
            time.sleep(SLEEP_OK)
            if not data: break
            events = data if isinstance(data, list) else data.get("data", [])
            if not events: break
            for ev in events:
                created = (ev.get("createdAt") or "")[:10]
                if created and created < DISC_SINCE:
                    stop = True; break
                ev_slug = ev.get("slug","")
                for mkt in ev.get("markets", []):
                    cid = mkt.get("conditionId","")
                    if not cid or cid in seen: continue
                    end_raw = mkt.get("endDate","") or mkt.get("end_date","")
                    try:
                        end_ts = pd.Timestamp(end_raw)
                        if pd.isna(end_ts):
                            continue
                        end_date = end_ts.date()
                    except Exception:
                        continue
                    # Only keep markets ending in our window
                    if not (win_start_dt <= end_date < win_end_dt):
                        continue
                    if not DATED_RE.search(ev_slug):
                        continue
                    tok_raw = mkt.get("clobTokenIds",[])
                    if isinstance(tok_raw, str):
                        try: tok_raw = json.loads(tok_raw)
                        except: tok_raw = []
                    seen[cid] = {
                        "condition_id": cid,
                        "token_ids":    tok_raw,
                        "slug":         mkt.get("slug",""),
                        "question":     mkt.get("question",""),
                        "event_slug":   ev_slug,
                        "end_date":     str(end_date),
                    }
            if len(events) < PAGE_EVENTS: break
            oldest = min((e.get("createdAt",""))[:10] for e in events)
            if oldest and oldest < DISC_SINCE: break
            offset += PAGE_EVENTS
        print(f"  tag={tag!r}: {len(seen)} markets so far in window", flush=True)

    return list(seen.values())


def fetch_trades(mkt):
    cid  = mkt["condition_id"]
    ckpt = load_ckpt(cid)
    if ckpt.get("done"):
        jl = jsonl_path(cid)
        raw = []
        if jl.exists():
            for line in jl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try: raw.append(json.loads(line))
                    except: pass
        return raw

    jl = jsonl_path(cid)
    jl.write_text("", encoding="utf-8")
    all_raw = []; offset = 0; n_pages = 0

    while n_pages < MAX_PAGES:
        params = {"market": cid, "limit": PAGE_TRADES, "offset": offset}
        resp   = get_json(f"{DATA_API}/trades", params=params)
        time.sleep(SLEEP_OK)
        n_pages += 1
        if not resp: break
        page = resp if isinstance(resp, list) else []
        if not page: break
        with open(jl, "a", encoding="utf-8") as f:
            for t in page: f.write(json.dumps(t) + "\n")
        all_raw.extend(page)
        if len(page) < PAGE_TRADES: break
        oldest_ts = min(t.get("timestamp", 9e18) for t in page)
        if oldest_ts < WIN_START - 86400 * 7:  # 1 week before window: stop
            break
        offset += PAGE_TRADES

    save_ckpt(cid, {"done": True, "n_raw": len(all_raw)})
    return all_raw


def normalize(raw, mkt):
    ts = raw.get("timestamp", 0)
    try: ts_int = int(ts)
    except: return None
    # Keep only trades in [WIN_START, WIN_END)
    if ts_int < WIN_START or ts_int >= WIN_END:
        return None
    price = raw.get("price", 0)
    try: price = float(price)
    except: price = float("nan")
    outcome = raw.get("outcome","Yes")
    price_yes = price if outcome != "No" else (1.0 - price)
    size = raw.get("size", 0)
    try: size = float(size)
    except: size = float("nan")
    usdc = size * price if not (math.isnan(size) or math.isnan(price)) else float("nan")
    return {
        "timestamp":    pd.Timestamp(ts_int * 1_000_000_000, unit="ns", tz="UTC"),
        "price_yes":    round(price_yes, 8),
        "price_raw":    round(price, 8),
        "size":         round(size, 8),
        "usdc_amount":  round(usdc, 8),
        "outcome":      outcome,
        "taker_side":   raw.get("side",""),
        "condition_id": raw.get("conditionId", mkt["condition_id"]),
        "token_id":     raw.get("asset",""),
        "market_slug":  raw.get("slug", mkt.get("slug","")),
        "event_slug":   mkt.get("event_slug",""),
        "question":     raw.get("title", mkt.get("question","")),
        "tx_hash":      raw.get("transactionHash",""),
        "proxy_wallet": raw.get("proxyWallet",""),
    }


def main():
    t0 = time.time()
    print(f"pm_gapfill_ext — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Window: {datetime.fromtimestamp(WIN_START,tz=timezone.utc).date()} -> "
          f"{datetime.fromtimestamp(WIN_END,tz=timezone.utc).date()}")

    print("\n[discover]")
    markets = discover_markets()
    print(f"  {len(markets)} markets in Feb-Mar 2026 window")
    by_ev = {}
    for m in markets:
        ev = m["event_slug"]
        by_ev.setdefault(ev, 0); by_ev[ev] += 1
    print(f"  {len(by_ev)} unique event slugs")
    for ev, cnt in sorted(by_ev.items(), key=lambda x: x[0]):
        print(f"    {ev}: {cnt} markets")

    if not markets:
        print("No markets found — exiting.")
        return

    print(f"\n[fetch] {len(markets)} markets...")
    all_norm = []; n_with = 0; n_empty = 0; n_resumed = 0

    for i, mkt in enumerate(markets, 1):
        was_done = load_ckpt(mkt["condition_id"]).get("done", False)
        raw_list = fetch_trades(mkt)
        if was_done: n_resumed += 1
        norm = [normalize(t, mkt) for t in raw_list]
        norm = [t for t in norm if t is not None]
        if norm: all_norm.extend(norm); n_with += 1
        else: n_empty += 1
        if i % 20 == 0 or i == len(markets):
            print(f"  [{i:>3}/{len(markets)}] {time.time()-t0:>5.0f}s  "
                  f"trades={len(all_norm):,}  with={n_with}  empty={n_empty}", flush=True)

    if not all_norm:
        print("No trades in window — done.")
        return

    new_df = pd.DataFrame(all_norm)
    new_df = new_df.drop_duplicates(subset=["tx_hash","token_id"]).reset_index(drop=True)
    bad = ~new_df["price_yes"].between(0.0, 1.0, inclusive="both")
    if bad.any():
        print(f"  Dropping {bad.sum()} rows outside [0,1]")
        new_df = new_df[~bad].reset_index(drop=True)

    print(f"\n[append] {len(new_df):,} new trades ({new_df['timestamp'].min().date()} "
          f"-> {new_df['timestamp'].max().date()})")

    # Load existing and merge
    existing = pd.read_parquet(OUT_PARQUET)
    before   = len(existing)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["tx_hash","token_id"]).reset_index(drop=True)
    combined = combined.sort_values("timestamp").reset_index(drop=True)
    combined.to_parquet(OUT_PARQUET, index=False)

    elapsed = time.time() - t0
    print(f"\n[done]")
    print(f"  Existing rows:  {before:,}")
    print(f"  New rows added: {len(combined)-before:,}")
    print(f"  Total rows:     {len(combined):,}")
    print(f"  Date range:     {combined['timestamp'].min().date()} -> {combined['timestamp'].max().date()}")
    print(f"  Elapsed:        {elapsed:.0f}s")
    print(f"  Output:         {OUT_PARQUET}")


if __name__ == "__main__":
    main()
