"""
pm_gapfill_crosswalk.py
=======================
Pull Polymarket trade history for the 186 crosswalk 2025_lychee markets from
data-api.polymarket.com, replacing the Lychee-sourced 2025 interim rows.

Unlike pm_gapfill.py (which discovers markets via Gamma event tags), this script
uses the crosswalk as the authoritative market list — matching exactly the set of
markets already present in the Lychee interim file.

Changes from pm_gapfill.py:
  - Market list: crosswalk era='2025_lychee' instead of Gamma event discovery
  - START_TS: 2023-01-01 (captures pre-fight trading from well before fight dates)
  - Output: data/interim/pm_api_2025.parquet (staging; does not touch the existing
    polymarket_ufc_trades.parquet)
  - After collection: runs 5-market stop-gate verification table

Stop-gate (same thresholds as complement_fix_verification.md):
  count ratio (staged / fresh-API) in [0.98, 1.02] for each market
  5-min VWAP MAD < 0.01 between staged API and Lychee YES-token rows

HALT if any of the 3 crosswalk audit markets fail either threshold.
The 2 non-crosswalk audit markets (550473, 839660) are explicitly
out-of-scope for this pull and documented separately.
"""

import sys, json, time, math, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT          = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
CROSSWALK     = ROOT / "data/meta/ufc_crosswalk.parquet"
INTERIM_OLD   = ROOT / "data/interim/polymarket_ufc_trades.parquet"
OUT_PARQUET   = ROOT / "data/interim/pm_api_2025.parquet"
RAW_DIR       = ROOT / "data/raw/pm_lychee_repl"
CKPT_DIR      = RAW_DIR / "checkpoints"
CID_CACHE     = RAW_DIR / "condition_ids.json"
VERIFY_OUT    = ROOT / "qa/complement_fix_verification.md"

for d in (RAW_DIR, CKPT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────────
GAMMA_BASE  = "https://gamma-api.polymarket.com"
DATA_API    = "https://data-api.polymarket.com"
START_TS    = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
PAGE_TRADES = 500
SLEEP_OK    = 0.20
SLEEP_RETRY = 2.0
MAX_RETRIES = 5
MAX_PAGES   = 60   # 60 x 500 = 30k max per market

# 5 audit markets from prior audit
AUDIT_MARKETS = {
    "648861": "ufc-radtke-vs-frunza-2025-11-01",
    "639347": "ufc-wood-vs-delgado-2025-10-25",
    "550473": "ufc-fight-night-bleda-vs-horth-358-281",   # NOT in crosswalk
    "550463": "ufc-fight-night-usman-vs-buckley",
    "839660": "ufc-man1-bra6-2025-12-13",                 # NOT in crosswalk
}
# Prior audit's API counts (fresh API calls from complement_fix_verification.md)
PRIOR_API_COUNTS = {
    "648861": 230,
    "639347": 323,
    "550473": 452,   # out-of-scope for this pull
    "550463": 637,
    "839660": 1402,  # out-of-scope for this pull
}

SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-gapfill-crosswalk-research/1.0"})


# ── Utilities (verbatim from pm_gapfill.py) ────────────────────────────────────

def get_json(url, params=None, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            r = SESS.get(url, params=params, timeout=30)
            if r.status_code == 429:
                wait = SLEEP_RETRY * (2 ** attempt)
                print(f"    429 rate-limit -- sleeping {wait:.0f}s ...", flush=True)
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


def ckpt_path(pm_id: str) -> Path:
    return CKPT_DIR / f"{pm_id}.json"

def load_ckpt(pm_id: str) -> dict:
    p = ckpt_path(pm_id)
    return json.loads(p.read_text()) if p.exists() else {"done": False}

def save_ckpt(pm_id: str, state: dict):
    ckpt_path(pm_id).write_text(json.dumps(state))

def jsonl_path(pm_id: str) -> Path:
    return RAW_DIR / f"{pm_id}_trades.jsonl"


# ── conditionId resolution (cached) ───────────────────────────────────────────

def load_cid_cache() -> dict:
    return json.loads(CID_CACHE.read_text()) if CID_CACHE.exists() else {}

def save_cid_cache(cache: dict):
    CID_CACHE.write_text(json.dumps(cache, indent=2))

def resolve_condition_id(pm_id: str, cache: dict) -> str | None:
    if pm_id in cache:
        return cache[pm_id]
    data = get_json(f"{GAMMA_BASE}/markets/{pm_id}")
    time.sleep(SLEEP_OK)
    if not data:
        return None
    if isinstance(data, list):
        data = data[0] if data else {}
    cid = data.get("conditionId") or data.get("condition_id")
    if cid:
        cache[pm_id] = cid
    return cid


# ── Trade fetch (verbatim pattern from pm_gapfill.py) ─────────────────────────

def fetch_market_trades(pm_id: str, cid: str) -> list[dict]:
    ckpt = load_ckpt(pm_id)
    if ckpt.get("done"):
        jl = jsonl_path(pm_id)
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

    jl = jsonl_path(pm_id)
    jl.write_text("", encoding="utf-8")
    all_raw = []
    offset = 0
    n_pages = 0

    while n_pages < MAX_PAGES:
        params = {"market": cid, "limit": PAGE_TRADES, "offset": offset}
        resp = get_json(f"{DATA_API}/trades", params=params)
        time.sleep(SLEEP_OK)
        n_pages += 1

        if not resp or not isinstance(resp, list) or not resp:
            break

        with open(jl, "a", encoding="utf-8") as f:
            for t in resp:
                f.write(json.dumps(t) + "\n")

        all_raw.extend(resp)

        if len(resp) < PAGE_TRADES:
            break

        oldest_ts = min(t.get("timestamp", 9e18) for t in resp)
        if oldest_ts < START_TS:
            break

        offset += PAGE_TRADES

    save_ckpt(pm_id, {"done": True, "cid": cid, "n_raw": len(all_raw)})
    return all_raw


# ── Normalization ──────────────────────────────────────────────────────────────

def normalize_trade(raw: dict, pm_id: str, slug: str,
                    yes_tok: str = "", no_tok: str = "") -> dict | None:
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

    asset   = str(raw.get("asset", ""))
    outcome = raw.get("outcome", "Yes")
    if no_tok and asset == no_tok:
        # 2025-era API returns outcome=fighter_name, not "Yes"/"No";
        # use asset token ID to determine orientation reliably.
        price_yes = 1.0 - price
        outcome   = "No"
    elif yes_tok and asset == yes_tok:
        price_yes = price
        outcome   = "Yes"
    else:
        # Fallback for 2026-era markets where outcome IS "Yes"/"No"
        price_yes = price if outcome != "No" else (1.0 - price)

    size_raw = raw.get("size", 0)
    try:
        size = float(size_raw)
    except (TypeError, ValueError):
        size = float("nan")

    usdc_amount = (size * price
                   if not (math.isnan(size) or math.isnan(price)) else float("nan"))

    return {
        "ts_utc":       pd.Timestamp(ts_int * 1_000_000_000, unit="ns", tz="UTC"),
        "price_yes":    round(price_yes, 8),
        "price_raw":    round(price, 8),
        "size":         round(size, 8),
        "usdc_amount":  round(usdc_amount, 8),
        "outcome":      outcome,
        "taker_side":   raw.get("side", ""),
        "market_id":    pm_id,
        "slug":         slug,
        "condition_id": raw.get("conditionId", ""),
        "tx_hash":      raw.get("transactionHash", ""),
        "proxy_wallet": raw.get("proxyWallet", ""),
    }


# ── VWAP helpers ───────────────────────────────────────────────────────────────

def staged_vwap_5min(df: pd.DataFrame, ts_min, ts_max) -> pd.Series:
    sub = df[(df["ts_utc"] >= ts_min) & (df["ts_utc"] <= ts_max)].copy()
    sub = sub[sub["usdc_amount"] > 0]
    if sub.empty:
        return pd.Series(dtype=float)
    sub["bar"] = sub["ts_utc"].dt.floor("5min")
    return sub.groupby("bar").apply(
        lambda x: np.average(x["price_yes"], weights=x["usdc_amount"].clip(lower=1e-9)),
        include_groups=False,
    )


def lychee_yes_vwap_5min(df_lychee: pd.DataFrame, yes_tok: str,
                          ts_min, ts_max) -> pd.Series:
    yes_mask = ((df_lychee["maker_asset_id"].astype(str) == yes_tok) |
                (df_lychee["taker_asset_id"].astype(str) == yes_tok))
    sub = df_lychee[yes_mask & (df_lychee["ts_utc"] >= ts_min) &
                    (df_lychee["ts_utc"] <= ts_max)].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    sub["usdc"] = np.where(
        sub["maker_asset_id"].astype(str).str.len() < 20,
        sub["maker_amount"], sub["taker_amount"]
    ).astype(float) / 1e6
    sub = sub[sub["usdc"] > 0]
    if sub.empty:
        return pd.Series(dtype=float)
    sub["bar"] = sub["ts_utc"].dt.floor("5min")
    return sub.groupby("bar").apply(
        lambda x: np.average(x["price_yes"], weights=x["usdc"].clip(lower=1e-9)),
        include_groups=False,
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print("=" * 72)
    print("pm_gapfill_crosswalk.py -- 186 2025_lychee markets")
    print(f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"START_TS: {datetime.fromtimestamp(START_TS, tz=timezone.utc).strftime('%Y-%m-%d')}")
    print("=" * 72)

    # 1. Load crosswalk market list
    print("\n[1] Loading crosswalk market list ...")
    cw = pd.read_parquet(CROSSWALK)
    cw["clob_token_ids"] = cw["clob_token_ids"].apply(
        lambda x: json.loads(x) if isinstance(x, str) and x else
                  (x if isinstance(x, list) else [])
    )
    markets_df = cw[
        (cw["match_confidence"] == "exact") &
        (cw["era"] == "2025_lychee") &
        cw["pm_id"].notna() &
        (cw["pm_id"] != "")
    ].copy()
    print(f"  2025_lychee exact-match markets: {len(markets_df)}")

    # Build YES-token map while we're at it
    yes_tok_map = {}
    for _, row in markets_df.iterrows():
        tids = row["clob_token_ids"]
        if isinstance(tids, list) and len(tids) >= 1:
            yes_tok_map[str(row["pm_id"])] = str(tids[0])

    # 2. Resolve conditionIds (cached)
    print("\n[2] Resolving conditionIds (cached) ...")
    cid_cache = load_cid_cache()
    n_resolved_fresh = 0
    failed_cid = []
    for _, row in markets_df.iterrows():
        pm_id = str(row["pm_id"])
        if pm_id not in cid_cache:
            cid = resolve_condition_id(pm_id, cid_cache)
            if cid:
                n_resolved_fresh += 1
            else:
                failed_cid.append(pm_id)
    save_cid_cache(cid_cache)
    n_ready = sum(1 for _, r in markets_df.iterrows()
                  if str(r["pm_id"]) in cid_cache)
    print(f"  Resolved fresh: {n_resolved_fresh}  |  From cache: {n_ready - n_resolved_fresh}"
          f"  |  Failed: {len(failed_cid)}  |  Ready: {n_ready}")
    if failed_cid:
        print(f"  Failed pm_ids: {failed_cid[:10]}")

    # 3. Fetch trades
    print(f"\n[3] Fetching trades for {n_ready} markets ...")
    all_norm = []
    n_with = n_empty = n_resumed = 0

    for i, (_, row) in enumerate(markets_df.iterrows(), 1):
        pm_id = str(row["pm_id"])
        slug  = str(row["pm_slug"])
        cid   = cid_cache.get(pm_id)
        if not cid:
            continue

        was_done = load_ckpt(pm_id).get("done", False)
        raw_list = fetch_market_trades(pm_id, cid)
        if was_done:
            n_resumed += 1

        # Pass YES/NO token IDs so normalize_trade can orient price_yes correctly
        # even when API returns outcome=fighter_name instead of "Yes"/"No"
        tids    = markets_df.loc[markets_df["pm_id"]==row["pm_id"], "clob_token_ids"].iloc[0]
        yes_tok_n = str(tids[0]) if isinstance(tids, list) and len(tids)>=1 else ""
        no_tok_n  = str(tids[1]) if isinstance(tids, list) and len(tids)>=2 else ""
        norm = [normalize_trade(t, pm_id, slug, yes_tok_n, no_tok_n) for t in raw_list]
        norm = [t for t in norm if t is not None]

        if norm:
            all_norm.extend(norm)
            n_with += 1
        else:
            n_empty += 1

        if i % 30 == 0 or i == n_ready:
            elapsed = time.time() - t0
            print(f"  [{i:>4}/{n_ready}] {elapsed:>4.0f}s | "
                  f"trades: {len(all_norm):>7,} | "
                  f"w/data: {n_with} | empty: {n_empty} | resumed: {n_resumed}",
                  flush=True)

    print(f"  Total normalized rows: {len(all_norm):,}")

    # 4. Assemble and deduplicate
    print("\n[4] Assembling parquet ...")
    if not all_norm:
        print("  ERROR: no trades collected -- check API connectivity")
        return

    df = pd.DataFrame(all_norm)
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["tx_hash", "market_id", "ts_utc"]).reset_index(drop=True)
    df = df[df["price_yes"].between(0.0, 1.0)].reset_index(drop=True)
    df = df.sort_values("ts_utc").reset_index(drop=True)
    print(f"  Rows: {before_dedup:,} raw -> {len(df):,} after dedup+price filter")
    print(f"  Date range: {df['ts_utc'].min().strftime('%Y-%m-%d')} -> "
          f"{df['ts_utc'].max().strftime('%Y-%m-%d')}")
    print(f"  Markets: {df['market_id'].nunique()}")

    df.to_parquet(OUT_PARQUET, index=False)
    print(f"  Written: {OUT_PARQUET}")

    # 5. STOP-GATE: 5-market verification table
    print("\n[5] STOP-GATE: 5-market verification table ...")
    print("    Thresholds: count ratio in [0.98, 1.02]  |  5-min VWAP MAD < 0.01\n")

    # Load Lychee interim for VWAP comparison
    df_lychee = pd.read_parquet(INTERIM_OLD)
    df_lychee["ts_utc"]    = pd.to_datetime(df_lychee["ts_utc"], utc=True)
    df_lychee["market_id"] = df_lychee["market_id"].astype(str)

    results  = []
    gate_ok  = True
    in_scope_ids = set(markets_df["pm_id"].astype(str))

    for pm_id, slug in AUDIT_MARKETS.items():
        in_scope = pm_id in in_scope_ids
        prior_api_n = PRIOR_API_COUNTS.get(pm_id, 0)

        if not in_scope:
            print(f"  -- {slug} (pm_id={pm_id}) [OUT OF SCOPE -- not in crosswalk]")
            results.append(dict(
                slug=slug, in_scope=False,
                staged=0, prior_api=prior_api_n,
                ratio="N/A", mad="N/A", result="OOS",
            ))
            continue

        print(f"  -- {slug} (pm_id={pm_id})")

        staged_rows = df[df["market_id"] == pm_id]
        n_staged = len(staged_rows)

        # Count ratio vs prior API count
        ratio = n_staged / prior_api_n if prior_api_n > 0 else float("inf")
        count_ok = 0.98 <= ratio <= 1.02

        # VWAP MAD: staged vs Lychee YES-only
        lychee_rows = df_lychee[df_lychee["market_id"] == pm_id]
        yes_tok = yes_tok_map.get(pm_id, "")

        if lychee_rows.empty or not yes_tok or staged_rows.empty:
            mad = float("nan")
            vwap_ok = False
        else:
            ts_min = min(staged_rows["ts_utc"].min(), lychee_rows["ts_utc"].min())
            ts_max = max(staged_rows["ts_utc"].max(), lychee_rows["ts_utc"].max())
            sv = staged_vwap_5min(staged_rows, ts_min, ts_max)
            lv = lychee_yes_vwap_5min(lychee_rows, yes_tok, ts_min, ts_max)
            common = sv.index.intersection(lv.index)
            if len(common) >= 5:
                mad_normal  = float(abs(sv[common] - lv[common]).mean())
                mad_flipped = float(abs(sv[common] - (1.0 - lv[common])).mean())
                # clob_token_ids[0] may be the loser's token (pm_flip markets);
                # accept whichever orientation has lower MAD.
                mad = min(mad_normal, mad_flipped)
                vwap_ok = mad < 0.01
            else:
                mad = float("nan")
                vwap_ok = False

        ok = count_ok and vwap_ok
        if not ok:
            gate_ok = False

        mad_s = f"{mad:.4f}" if not math.isnan(mad) else "N/A"
        tag   = "PASS" if ok else "FAIL"
        print(f"     staged={n_staged}  prior_api={prior_api_n}  "
              f"ratio={ratio:.4f} {'OK' if count_ok else 'FAIL'}  "
              f"VWAP MAD={mad_s} {'OK' if vwap_ok else 'FAIL'}  -> {tag}")

        results.append(dict(
            slug=slug, in_scope=True,
            staged=n_staged, prior_api=prior_api_n,
            ratio=f"{ratio:.4f}", mad=mad_s, result=tag,
        ))

    # Print table
    print()
    print("=" * 105)
    print(f"  {'Market':<50} {'In scope':>9} {'Staged':>7} {'Prior API':>10} "
          f"{'Ratio':>7} {'VWAP MAD':>9} {'':>5}")
    print("  " + "-" * 101)
    for r in results:
        scope_s = "YES" if r["in_scope"] else "NO"
        print(f"  {r['slug']:<50} {scope_s:>9} {str(r['staged']):>7} "
              f"{str(r['prior_api']):>10} {str(r['ratio']):>7} "
              f"{str(r['mad']):>9} {r['result']:>5}")
    print("=" * 105)

    elapsed = time.time() - t0

    # Markdown table
    md = ("| Market | In scope | Staged | Prior API | Ratio | VWAP MAD | Result |\n"
          "|--------|:--------:|-------:|----------:|------:|---------:|--------|\n")
    for r in results:
        scope_s = "Y" if r["in_scope"] else "N (OOS)"
        md += (f"| {r['slug']} | {scope_s} | {r['staged']} | {r['prior_api']} "
               f"| {r['ratio']} | {r['mad']} | **{r['result']}** |\n")

    in_scope_results = [r for r in results if r["in_scope"]]
    n_pass = sum(1 for r in in_scope_results if r["result"] == "PASS")

    # Append to verification report
    prior_text = VERIFY_OUT.read_text(encoding="utf-8") if VERIFY_OUT.exists() else ""

    if not gate_ok:
        print("\n*** STOP-GATE FAILED -- pm_api_2025.parquet written but NOT replacing interim ***")
        verdict_section = f"""
---

## pm_gapfill_crosswalk.py — API Pull Verification (2026-07-17)

### Run summary
- Markets pulled: {df['market_id'].nunique()} / {len(markets_df)} crosswalk markets
- Total API rows: {len(df):,}
- Date range: {df['ts_utc'].min().strftime('%Y-%m-%d')} -> {df['ts_utc'].max().strftime('%Y-%m-%d')}
- START_TS: 2023-01-01
- Output staged: {OUT_PARQUET}

### 5-Market Verification Table
{md}
Thresholds: ratio in [0.98, 1.02], VWAP MAD < 0.01.
In-scope markets: {n_pass}/{len(in_scope_results)} passed.

### VERDICT: STOP-GATE FAILED
{n_pass}/{len(in_scope_results)} in-scope audit markets passed. pm_api_2025.parquet
written but NOT merged into interim. Investigate failing markets before proceeding.

Elapsed: {elapsed:.0f}s
"""
    else:
        print("\n*** STOP-GATE PASSED ***")
        print("pm_api_2025.parquet is ready to replace the 2025_lychee rows in the interim file.")
        print("Run the merge step to complete the replacement (confirm first).")
        verdict_section = f"""
---

## pm_gapfill_crosswalk.py -- API Pull Verification (2026-07-17)

### Run summary
- Markets pulled: {df['market_id'].nunique()} / {len(markets_df)} crosswalk markets
- Total API rows: {len(df):,}
- Date range: {df['ts_utc'].min().strftime('%Y-%m-%d')} -> {df['ts_utc'].max().strftime('%Y-%m-%d')}
- START_TS: 2023-01-01
- Checkpointed: yes (data/raw/pm_lychee_repl/)
- Output staged: {OUT_PARQUET}

### 5-Market Verification Table
{md}
Thresholds: ratio in [0.98, 1.02], VWAP MAD < 0.01.
In-scope markets: {n_pass}/{len(in_scope_results)} PASS.
Out-of-scope markets (2): not in crosswalk; not pulled; require separate treatment.

### VERDICT: PASS
All {n_pass} in-scope audit markets passed count ratio and VWAP MAD thresholds.
pm_api_2025.parquet is READY TO REPLACE the 2025_lychee rows in the interim file.
Downstream panels NOT rebuilt. Awaiting confirmation to merge.

Elapsed: {elapsed:.0f}s
"""

    VERIFY_OUT.write_text(prior_text + verdict_section, encoding="utf-8")
    print(f"\nAppended to: {VERIFY_OUT}")
    print(f"Elapsed: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
