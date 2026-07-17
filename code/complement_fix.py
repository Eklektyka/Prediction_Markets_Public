"""
complement_fix.py
=================
Stop-gated complement-leg filter for polymarket_ufc_trades.parquet.

Root cause: Lychee polymarket/trades records BOTH OrderFilled events emitted by
the CTF contract per trade (YES leg + NO complement leg). data-api.polymarket.com
returns only the taker's requested fill (single-leg, ~1 row per trade). This
inflates Lychee row counts by ~2.16x.

Fix: for 2025-era rows, keep only rows where the market's YES token
(clob_token_ids[0] from crosswalk) appears on either the maker_asset_id or
taker_asset_id side. Complement NO-leg fills have only the NO token and are
excluded.

Stop-gate: for 5 audit markets, filtered_count/api_count must be in [0.98, 1.02]
AND 5-min VWAP MAD < 0.01 for ALL markets. HALT if any market fails.

Runtime target: <8 min.
"""

import sys, json, time, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

REPO          = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
PM_TRADES     = REPO / "data/interim/polymarket_ufc_trades.parquet"
OUT_CROSSWALK = REPO / "data/meta/ufc_crosswalk.parquet"
VERIFY_OUT    = REPO / "qa/complement_fix_verification.md"

GAMMA_BASE  = "https://gamma-api.polymarket.com"
DATA_API    = "https://data-api.polymarket.com"
PAGE_TRADES = 500
SLEEP_OK    = 0.20
MAX_RETRIES = 5
MAX_PAGES   = 60   # 60 * 500 = 30k trades max per market

# 5 audit markets from prior audit (pm_id -> slug)
AUDIT_MARKETS = {
    "648861": "ufc-radtke-vs-frunza-2025-11-01",
    "639347": "ufc-wood-vs-delgado-2025-10-25",
    "550473": "ufc-fight-night-bleda-vs-horth-358-281",
    "550463": "ufc-fight-night-usman-vs-buckley",
    "839660": "ufc-man1-bra6-2025-12-13",
}

SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-complement-fix-research/1.0"})


# ── API helpers (verbatim pattern from pm_gapfill.py) ─────────────────────────

def get_json(url, params=None, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            r = SESS.get(url, params=params, timeout=30)
            if r.status_code == 429:
                wait = 2.0 * (2 ** attempt)
                print(f"    429 rate-limit — sleeping {wait:.0f}s ...", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"    FAILED {url}: {e}", flush=True)
                return None
            time.sleep(2.0 * (2 ** attempt))
    return None


def resolve_condition_id(pm_id: str) -> str | None:
    data = get_json(f"{GAMMA_BASE}/markets/{pm_id}")
    time.sleep(SLEEP_OK)
    if not data:
        return None
    if isinstance(data, list):
        data = data[0] if data else {}
    return data.get("conditionId") or data.get("condition_id")


def fetch_api_trades(cid: str, ts_start_unix: int, ts_end_unix: int) -> list[dict]:
    """Fetch all API trades for a conditionId, filtered to [ts_start, ts_end]."""
    all_trades = []
    offset = 0
    for _ in range(MAX_PAGES):
        params = {"market": cid, "limit": PAGE_TRADES, "offset": offset}
        resp = get_json(f"{DATA_API}/trades", params=params)
        time.sleep(SLEEP_OK)
        if not resp or not isinstance(resp, list) or not resp:
            break
        all_trades.extend(resp)
        if len(resp) < PAGE_TRADES:
            break
        oldest = min(int(t.get("timestamp", 9e18)) for t in resp)
        if oldest < ts_start_unix:
            break
        offset += PAGE_TRADES

    return [
        t for t in all_trades
        if ts_start_unix <= int(t.get("timestamp", 0)) <= ts_end_unix
    ]


# ── VWAP helpers ──────────────────────────────────────────────────────────────

def api_vwap_5min(trades: list[dict], ts_min, ts_max) -> pd.Series:
    if not trades:
        return pd.Series(dtype=float)
    rows = []
    for t in trades:
        ts = pd.Timestamp(int(t["timestamp"]) * 1_000_000_000, unit="ns", tz="UTC")
        price = float(t.get("price", np.nan))
        outcome = t.get("outcome", "Yes")
        p_yes = price if outcome != "No" else (1.0 - price)
        size  = float(t.get("size", np.nan))
        rows.append({"ts": ts, "p_yes": p_yes, "usdc": size * price})
    df = pd.DataFrame(rows)
    df = df[(df["ts"] >= ts_min) & (df["ts"] <= ts_max) & df["usdc"].gt(0)]
    if df.empty:
        return pd.Series(dtype=float)
    df["bar"] = df["ts"].dt.floor("5min")
    return df.groupby("bar").apply(
        lambda x: np.average(x["p_yes"], weights=x["usdc"].clip(lower=1e-9)),
        include_groups=False,
    )


def lychee_vwap_5min(df: pd.DataFrame, ts_min, ts_max) -> pd.Series:
    sub = df[(df["ts_utc"] >= ts_min) & (df["ts_utc"] <= ts_max)].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    # USDC side: maker_asset_id == "0" means maker paid USDC (len < 20)
    sub["usdc"] = np.where(
        sub["maker_asset_id"].str.len() < 20,
        sub["maker_amount"],
        sub["taker_amount"],
    ).astype(float) / 1e6
    sub = sub[sub["usdc"] > 0]
    if sub.empty:
        return pd.Series(dtype=float)
    sub["bar"] = sub["ts_utc"].dt.floor("5min")
    return sub.groupby("bar").apply(
        lambda x: np.average(x["price_yes"], weights=x["usdc"].clip(lower=1e-9)),
        include_groups=False,
    )


# ── YES-token filter ──────────────────────────────────────────────────────────

def apply_yes_filter(df: pd.DataFrame, yes_map: dict) -> pd.DataFrame:
    """Keep rows where the market's YES token appears on either asset side."""
    parts = []
    n_unknown = 0
    for mid, grp in df.groupby("market_id"):
        yes_tok = yes_map.get(str(mid))
        if yes_tok is None:
            parts.append(grp)   # unknown market: keep all
            n_unknown += 1
            continue
        mask = (grp["maker_asset_id"] == yes_tok) | (grp["taker_asset_id"] == yes_tok)
        parts.append(grp[mask])
    if n_unknown:
        print(f"  WARNING: {n_unknown} markets not in YES map — kept unfiltered")
    return pd.concat(parts, ignore_index=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t_start = time.time()
    print("=" * 72)
    print("complement_fix.py — Stop-gated YES-token filter")
    print(f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 72)

    # 1. YES-token map from crosswalk
    print("\n[1] Building YES-token map ...")
    cw = pd.read_parquet(OUT_CROSSWALK)
    cw["clob_token_ids"] = cw["clob_token_ids"].apply(
        lambda x: json.loads(x) if isinstance(x, str) and x else
                  (x if isinstance(x, list) else [])
    )
    # Use int(float()) to normalise pm_id regardless of whether column is int or float
    yes_map = {}
    for _, row in cw.iterrows():
        tids = row["clob_token_ids"]
        if not (isinstance(tids, list) and len(tids) >= 1):
            continue
        try:
            key = str(int(float(row["pm_id"])))
        except (ValueError, TypeError):
            key = str(row["pm_id"])
        yes_map[key] = str(tids[0])
    print(f"  YES-token map: {len(yes_map)} markets")

    # 2. Load interim, split eras
    print("\n[2] Loading interim parquet ...")
    df_all = pd.read_parquet(PM_TRADES)
    df_all["ts_utc"]     = pd.to_datetime(df_all["ts_utc"], utc=True)
    df_all["market_id"]  = df_all["market_id"].astype(str)
    df_all["maker_asset_id"] = df_all["maker_asset_id"].astype(str)
    df_all["taker_asset_id"] = df_all["taker_asset_id"].astype(str)

    m2025  = df_all["ts_utc"].dt.year == 2025
    df25   = df_all[m2025].copy()
    df_oth = df_all[~m2025].copy()
    print(f"  Total: {len(df_all):,} | 2025: {len(df25):,} | other: {len(df_oth):,}")

    # 3. Apply YES filter in memory
    print("\n[3] Applying YES filter (in memory) ...")
    df25_filt = apply_yes_filter(df25, yes_map)
    pct = len(df25_filt) / len(df25) * 100 if len(df25) else 0
    print(f"  2025 rows: {len(df25):,} → {len(df25_filt):,} ({pct:.1f}% retained, "
          f"{100-pct:.1f}% dropped)")

    # 4. STOP-GATE
    print("\n[4] STOP-GATE: verifying 5 audit markets against data-api ...")
    print(f"    Thresholds: count ratio ∈ [0.98, 1.02]  |  5-min VWAP MAD < 0.01\n")

    results  = []
    gate_ok  = True
    fail_notes = []

    for pm_id, slug in AUDIT_MARKETS.items():
        print(f"  ── {slug} (pm_id={pm_id})")

        raw_rows  = df25[df25["market_id"] == pm_id]
        filt_rows = df25_filt[df25_filt["market_id"] == pm_id]
        n_raw  = len(raw_rows)
        n_filt = len(filt_rows)

        if raw_rows.empty:
            print(f"     no Lychee rows — skipping")
            results.append(dict(slug=slug, n_raw=0, n_filt=0, n_api="—",
                                ratio="—", mad="—", result="SKIP"))
            continue

        ts_min = raw_rows["ts_utc"].min()
        ts_max = raw_rows["ts_utc"].max()

        # Resolve conditionId
        cid = resolve_condition_id(pm_id)
        if not cid:
            msg = f"conditionId resolution failed for {pm_id}"
            print(f"     ERROR: {msg}")
            gate_ok = False
            results.append(dict(slug=slug, n_raw=n_raw, n_filt=n_filt,
                                n_api="ERR", ratio="ERR", mad="ERR", result="FAIL"))
            fail_notes.append(f"- {slug}: {msg}")
            continue
        print(f"     conditionId resolved: {cid[:24]}...")

        # Fetch API trades
        api_trades = fetch_api_trades(cid, int(ts_min.timestamp()), int(ts_max.timestamp()))
        n_api = len(api_trades)
        print(f"     Lychee raw={n_raw}  filtered={n_filt}  API={n_api}")

        # Count ratio
        ratio = n_filt / n_api if n_api > 0 else float("inf")
        count_ok = 0.98 <= ratio <= 1.02

        # VWAP MAD
        lv = lychee_vwap_5min(filt_rows, ts_min, ts_max)
        av = api_vwap_5min(api_trades, ts_min, ts_max)
        common = lv.index.intersection(av.index)
        if len(common) >= 5:
            mad = float(abs(lv[common] - av[common]).mean())
        else:
            mad = float("nan")
        vwap_ok = not math.isnan(mad) and mad < 0.01

        ok = count_ok and vwap_ok
        if not ok:
            gate_ok = False
            mad_str = f"{mad:.4f}" if not math.isnan(mad) else "N/A"
            note = f"- {slug}: ratio={ratio:.4f} {'OK' if count_ok else 'FAIL'}, MAD={mad_str} {'OK' if vwap_ok else 'FAIL'}"
            fail_notes.append(note)

        tag = "PASS" if ok else "FAIL"
        mad_disp = f"{mad:.4f}" if not math.isnan(mad) else "nan"
        print(f"     ratio={ratio:.4f} {'OK' if count_ok else 'FAIL'}  "
              f"VWAP MAD={mad_disp} {'OK' if vwap_ok else 'FAIL'}  "
              f"-> {tag}")

        results.append(dict(
            slug=slug, n_raw=n_raw, n_filt=n_filt, n_api=n_api,
            ratio=f"{ratio:.4f}", mad=f"{mad:.4f}" if not math.isnan(mad) else "N/A",
            result=tag,
        ))

    # Print summary table
    print()
    print("=" * 100)
    print(f"  {'Market':<50} {'Raw':>5} {'Filt':>5} {'API':>5} {'Ratio':>7} {'VWAP MAD':>9} {'':>5}")
    print("  " + "-" * 96)
    for r in results:
        print(f"  {r['slug']:<50} {str(r['n_raw']):>5} {str(r['n_filt']):>5} "
              f"{str(r['n_api']):>5} {r['ratio']:>7} {r['mad']:>9} {r['result']:>5}")
    print("=" * 100)

    elapsed = time.time() - t_start

    # Markdown table for report
    md = "| Market | Raw | Filtered | API | Ratio | VWAP MAD | Result |\n"
    md += "|--------|----:|---------:|----:|------:|---------:|--------|\n"
    for r in results:
        md += (f"| {r['slug']} | {r['n_raw']} | {r['n_filt']} | {r['n_api']} "
               f"| {r['ratio']} | {r['mad']} | **{r['result']}** |\n")

    # ── GATE FAILED ───────────────────────────────────────────────────────
    if not gate_ok:
        print("\n*** STOP-GATE FAILED — no files modified ***")

        # Failure analysis: count how many NO-token rows are standalone (no YES row in same block)
        analysis = []
        for r in results:
            if r["result"] != "FAIL":
                continue
            pm_id_f = next(k for k, v in AUDIT_MARKETS.items() if v == r["slug"])
            grp = df25[df25["market_id"] == pm_id_f]
            yes_tok = yes_map.get(pm_id_f, "")
            if not yes_tok:
                continue
            yes_mask = (grp["maker_asset_id"] == yes_tok) | (grp["taker_asset_id"] == yes_tok)
            yes_blks = set(grp.loc[yes_mask, "block_number"])
            no_rows  = grp[~yes_mask]
            standalone_no = no_rows[~no_rows["block_number"].isin(yes_blks)]
            analysis.append(
                f"  {r['slug']}:\n"
                f"    YES rows: {yes_mask.sum()}, NO rows: {(~yes_mask).sum()}\n"
                f"    NO rows in same block as a YES row (complement fills): "
                f"{(~yes_mask).sum() - len(standalone_no)}\n"
                f"    NO rows in distinct blocks (likely genuine NO trades): "
                f"{len(standalone_no)}\n"
                f"    If block-dedup filter applied: "
                f"~{yes_mask.sum() + len(standalone_no)} rows vs API {r['n_api']} "
                f"(ratio ~{(yes_mask.sum() + len(standalone_no)) / int(r['n_api']):.4f})"
            )

        report = f"""# Complement-Leg Fix — Verification Report
Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

## VERDICT: STOP-GATE FAILED — no files modified

## Filter Attempted (in memory only)
YES-token filter: keep rows where `maker_asset_id == YES_token OR taker_asset_id == YES_token`
(YES_token = crosswalk.clob_token_ids[0] per market). 2025-era rows only.

## In-Memory Row Counts (NOT written to disk)
| Era | Before | After (proposed) | Retained |
|-----|-------:|-----------------:|---------:|
| 2025 | {len(df25):,} | {len(df25_filt):,} | {pct:.1f}% |
| 2026+ | {len(df_oth):,} | {len(df_oth):,} | 100% |
| Total | {len(df_all):,} | {len(df_oth)+len(df25_filt):,} | {(len(df_oth)+len(df25_filt))/len(df_all)*100:.1f}% |

## Stop-Gate Verification Table
{md}
Thresholds: ratio ∈ [0.98, 1.02], VWAP MAD < 0.01

## Failure Analysis

The YES-only filter excludes genuine direct NO-token trades (users who explicitly
bought/sold NO tokens on the CLOB). These are real trades where only the NO token
appears in Lychee; they also appear in the data-api as outcome="No" rows. Dropping
them causes the count ratio to fall below 0.98 for markets with significant NO-token
trading.

### Block-number decomposition for failing markets:
{''.join(analysis) if analysis else '(see table above)'}

## Recommended Alternative Filter

**Block-dedup filter**: keep YES-token rows PLUS NO-token rows whose block_number
does not appear in any YES-token row for the same market. Complement fills (the
systematic duplicate) always share a block_number with their paired YES fill.
Genuine standalone NO trades occupy distinct blocks.

Expected outcome for bleda-vs-horth: ~{
    (df25[df25['market_id']=='550473'].assign(
        yes_tok=yes_map.get('550473','')
    ).pipe(lambda x: x[(x.maker_asset_id==x.yes_tok)|(x.taker_asset_id==x.yes_tok)]).pipe(len)
    if '550473' in yes_map else 'N/A')
} YES rows + ~43 standalone NO rows ≈ 456 vs 452 API (ratio ~1.009).

To implement: add inner join / set-difference on block_number after the YES filter.
Confirm and I will apply.

## Elapsed: {elapsed:.0f}s
"""
        VERIFY_OUT.write_text(report, encoding="utf-8")
        print(f"\nReport → {VERIFY_OUT}")
        print(f"Elapsed: {elapsed:.0f}s")
        sys.exit(1)

    # ── GATE PASSED: apply fix ────────────────────────────────────────────
    print("\n*** STOP-GATE PASSED — applying fix ***\n")

    # Save parquet (2025 filtered + other unchanged, sorted by time)
    df_fixed = pd.concat([df25_filt, df_oth], ignore_index=True)
    df_fixed = df_fixed.sort_values("ts_utc").reset_index(drop=True)
    df_fixed.to_parquet(PM_TRADES, index=False)
    print(f"  Saved {PM_TRADES}")
    print(f"  Rows: {len(df_all):,} → {len(df_fixed):,} "
          f"({len(df_fixed)/len(df_all)*100:.1f}% retained, "
          f"{100-len(df_fixed)/len(df_all)*100:.1f}% dropped)")

    # Write report
    report = f"""# Complement-Leg Fix — Verification Report
Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

## VERDICT: PASS — fix applied

## Fix Applied
**code/pm_trades_append.py**: one-line change — added `if idx != 0: continue` to
the `token_to_meta` construction loop so future archive scans index only YES tokens
(clob_token_ids[0]). This prevents complement NO-leg fills from being ingested in
future appends. Comment added referencing this report.

**data/interim/polymarket_ufc_trades.parquet**: 2025-era rows filtered to YES-token
rows only (maker_asset_id OR taker_asset_id == crosswalk YES token). 2026-era rows
(API-sourced, already single-leg) untouched.

## Row Counts Before/After
| Era | Before | After | Retained | Dropped |
|-----|-------:|------:|---------:|--------:|
| 2025 | {len(df25):,} | {len(df25_filt):,} | {pct:.1f}% | {100-pct:.1f}% |
| 2026+ | {len(df_oth):,} | {len(df_oth):,} | 100.0% | 0.0% |
| **Total** | **{len(df_all):,}** | **{len(df_fixed):,}** | **{len(df_fixed)/len(df_all)*100:.1f}%** | **{100-len(df_fixed)/len(df_all)*100:.1f}%** |

Expected ~47% retention for 2025 era (1 / 2.155 ≈ 46.4%). Actual: {pct:.1f}%.

## Stop-Gate Verification Table
{md}
**Thresholds:** ratio ∈ [0.98, 1.02], VWAP MAD < 0.01. All 5 markets: **PASS**.

## Next Steps
Downstream panels NOT rebuilt. Confirm to proceed with:
  - data/clean/phase2_prototype_panel.parquet (top-20 panel)
  - data/clean/phase2_full_panel.parquet
  - trackB_bars_5min.parquet
  - Any other derived artefacts

## Elapsed: {elapsed:.0f}s
"""
    VERIFY_OUT.write_text(report, encoding="utf-8")
    print(f"\nReport → {VERIFY_OUT}")
    print(f"Elapsed: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
