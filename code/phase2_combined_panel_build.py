"""
phase2_combined_panel_build.py
==============================
Combine 2025_lychee + 2026_collector eras into unified 5-min panel.

Era-specific data sources
  2025_lychee   — Kalshi: Lychee yes_price(0-100)/count
                  PM: polymarket_ufc_trades.parquet (market_id numeric, one-sided)
  2026_collector— Kalshi: data/raw/live/**  yes_price_dollars(0-1)/count_fp
                  PM: pm_gapfill_trades.parquet (condition_id hex, outcome=fighter name)

Critical architecture:
  2025 PM price already one-sided → invert with 1-price if pm_flip=True.
  2026 PM has BOTH fighters' trades in same condition_id → filter by
  outcome == fighters_pm[0] (or fighters_pm[1] if pm_flip=True). No 1-price inversion.

Outputs:
  data/clean/phase2_full_panel.parquet   (era column added)
  qa/phase2_side_audit.md
"""

import glob as _glob, json, re, sys, unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO   = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
LYCHEE = Path(r"C:\Kalshi_data\lychee\extracted\data")
LIVE   = REPO / "data/raw/live"

K_MARKETS_DIR = LYCHEE / "kalshi/markets"
K_TRADES_DIR  = LYCHEE / "kalshi/trades"
PM_2025       = REPO / "data/interim/polymarket_ufc_trades.parquet"
PM_2026       = REPO / "data/interim/pm_gapfill_trades.parquet"
K26_API       = REPO / "data/interim/kxufcfight_2026_markets.parquet"
XWALK         = REPO / "data/meta/ufc_crosswalk.parquet"
OVERRIDES_CSV = REPO / "data/meta/crosswalk_overrides.csv"
OUT_PANEL     = REPO / "data/clean/phase2_full_panel.parquet"
OUT_AUDIT     = REPO / "qa/phase2_side_audit.md"
OUT_PANEL.parent.mkdir(parents=True, exist_ok=True)
OUT_AUDIT.parent.mkdir(parents=True, exist_ok=True)

BAR_FREQ  = "5min"
MAX_FFILL = 12     # 12 × 5 min = 60 min max staleness
WIN_PRE   = 72     # hours before fight


# =============================================================================
# HELPERS
# =============================================================================

def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\s]", "", s.lower()).strip()

def name_overlap(a: str, b: str) -> int:
    return len(set(norm(a).split()) & set(norm(b).split()))

def parse_list(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return []
    if isinstance(x, list):
        return x
    try:
        v = json.loads(x)
        return v if isinstance(v, list) else []
    except Exception:
        return []

def make_bars(df: pd.DataFrame, time_col: str, price_col: str,
              weight_col: str, t_start, t_end) -> pd.DataFrame:
    sub = df[(df[time_col] >= t_start) & (df[time_col] <= t_end)].copy()
    if sub.empty:
        return pd.DataFrame(columns=["last", "vwap", "n", "vol"])
    sub["bar"]  = sub[time_col].dt.floor(BAR_FREQ)
    sub["px_w"] = sub[price_col] * sub[weight_col]
    grp = sub.groupby("bar", sort=True).agg(
        n       = (price_col,  "count"),
        last    = (price_col,  "last"),
        sum_pxw = ("px_w",     "sum"),
        vol     = (weight_col, "sum"),
    )
    grp["vwap"] = grp["sum_pxw"] / grp["vol"].replace(0, np.nan)
    return grp[["last", "vwap", "n", "vol"]]

def apply_stale_ffill(s: pd.Series, max_fill: int):
    s_ff  = s.ffill(limit=max_fill)
    stale = s.isna() & s_ff.notna()
    return s_ff, stale

def assemble_bars(fid: str, era: str, t_start, t_end,
                  kb: pd.DataFrame, pmb: pd.DataFrame):
    bar_idx = pd.date_range(t_start, t_end, freq=BAR_FREQ, tz="UTC", inclusive="left")
    kb  = kb.reindex(bar_idx)
    pmb = pmb.reindex(bar_idx)
    k_last_ff,  k_stale  = apply_stale_ffill(kb["last"],  MAX_FFILL)
    pm_last_ff, pm_stale = apply_stale_ffill(pmb["last"], MAX_FFILL)
    bars = pd.DataFrame({
        "fight_id": fid, "bar_utc": bar_idx, "era": era,
        "k_last":   k_last_ff,  "k_vwap":  kb["vwap"],
        "k_n":      kb["n"].fillna(0).astype(int),
        "k_vol":    kb["vol"].fillna(0),
        "k_stale":  k_stale.fillna(False),
        "pm_last":  pm_last_ff, "pm_vwap": pmb["vwap"],
        "pm_n":     pmb["n"].fillna(0).astype(int),
        "pm_vol":   pmb["vol"].fillna(0),
        "pm_stale": pm_stale.fillna(False),
    })
    bars = bars[bars["k_last"].notna() | bars["pm_last"].notna()].copy()
    bars["both_traded"] = (bars["k_n"] > 0) & (bars["pm_n"] > 0)
    return bars


# =============================================================================
# 0. LOAD OVERRIDES
# =============================================================================
print("[0] loading pm_flip overrides...", flush=True)
overrides_raw = pd.read_csv(OVERRIDES_CSV)
pm_flip_overrides: dict[str, bool] = {}
if "pm_flip_override" in overrides_raw.columns:
    for _, row in overrides_raw.dropna(subset=["pm_flip_override"]).iterrows():
        val = str(row["pm_flip_override"]).strip()
        if val in ("False", "false", "0"):
            pm_flip_overrides[row["fight_id"]] = False
        elif val in ("True", "true", "1"):
            pm_flip_overrides[row["fight_id"]] = True
print(f"  pm_flip_overrides: {pm_flip_overrides}", flush=True)


# =============================================================================
# 1. LOAD CROSSWALK
# =============================================================================
print("\n[1] loading crosswalk...", flush=True)
cw = pd.read_parquet(XWALK)
for col in ["fighters_kalshi", "tickers", "fighters_pm", "outcomes", "clob_token_ids"]:
    cw[col] = cw[col].apply(parse_list)

exact_all = cw[
    (cw["match_confidence"] == "exact") & cw["exclusion_reason"].isna()
].copy()
cw25 = exact_all[exact_all["era"] == "2025_lychee"].copy()
cw26 = exact_all[exact_all["era"] == "2026_collector"].copy()

print(f"  2025_lychee exact UFC fights: {len(cw25)}", flush=True)
print(f"  2026_collector exact UFC fights: {len(cw26)}", flush=True)


# =============================================================================
# 2. TICKER MAPS — 2025 (Lychee)
# =============================================================================
print("\n[2] building 2025 ticker maps (Lychee)...", flush=True)
ticker_to_name_25:  dict[str, str]          = {}
ticker_to_close_25: dict[str, pd.Timestamp] = {}
for f in sorted(K_MARKETS_DIR.glob("*.parquet")):
    try:
        df = pd.read_parquet(f, columns=["ticker", "title", "close_time"])
        ufc = df[df["ticker"].str.startswith("KXUFC", na=False)]
        for _, row in ufc.iterrows():
            tkr = row["ticker"]
            m = re.match(r"Will (.+?) win the .+ vs .+ professional MMA", row["title"])
            if m:
                ticker_to_name_25[tkr] = m.group(1).strip()
            ct = row.get("close_time")
            if ct is not None and pd.notna(ct):
                ts = pd.Timestamp(ct)
                ticker_to_close_25[tkr] = (ts.tz_localize("UTC") if ts.tzinfo is None
                                           else ts.tz_convert("UTC"))
    except Exception:
        continue
print(f"  {len(ticker_to_name_25)} ticker->name  |  {len(ticker_to_close_25)} ticker->close",
      flush=True)


# =============================================================================
# 3. TICKER MAPS — 2026 (Collector API cache)
# =============================================================================
print("\n[3] building 2026 ticker maps (Collector)...", flush=True)
k26_api = pd.read_parquet(K26_API)
ticker_to_name_26:  dict[str, str]          = {}
ticker_to_close_26: dict[str, pd.Timestamp] = {}
for _, row in k26_api.iterrows():
    tkr = str(row["ticker"])
    ct  = row.get("close_time")
    if ct is not None and pd.notna(ct):
        ts = pd.Timestamp(ct)
        if ts.tzinfo is None: ts = ts.tz_localize("UTC")
        ticker_to_close_26[tkr] = ts.tz_convert("UTC")
    title = str(row.get("title", ""))
    m = re.match(r"Will (.+?) win the", title)
    if m:
        ticker_to_name_26[tkr] = m.group(1).strip()
print(f"  {len(ticker_to_name_26)} ticker->name  |  {len(ticker_to_close_26)} ticker->close",
      flush=True)


# =============================================================================
# 4. BUILD FIGHT META — helper for both eras
# =============================================================================

def build_fight_meta(cw_era: pd.DataFrame, ticker_to_name: dict,
                     ticker_to_close: dict, era: str) -> list[dict]:
    meta = []
    n_flipped  = 0
    n_fallback = 0
    for _, fight in cw_era.iterrows():
        tickers    = fight["tickers"]    or []
        fighters_p = fight["fighters_pm"] or fight["outcomes"] or []
        pm_yes_name = fighters_p[0] if fighters_p else ""

        # Find ticker best matching fighters_pm[0]
        best_tkr_f0   = tickers[0] if tickers else ""
        best_score_f0 = -1
        for t in tickers:
            sc = name_overlap(pm_yes_name, ticker_to_name.get(t, ""))
            if sc > best_score_f0:
                best_score_f0 = sc; best_tkr_f0 = t

        fid = fight["fight_id"]
        if fid in pm_flip_overrides:
            pm_flip = pm_flip_overrides[fid]
        else:
            pm_flip = (best_score_f0 == 0 and len(tickers) >= 2)

        if pm_flip:
            n_flipped += 1
            # For 2026: yes_ticker should map to fighters_pm[1]
            # For 2025: yes_ticker still points to best for f0 (PM side flipped via 1-price)
            if era == "2026_collector" and len(fighters_p) >= 2:
                pm_alt_name   = fighters_p[1]
                best_tkr_f1   = tickers[0]
                best_score_f1 = -1
                for t in tickers:
                    sc = name_overlap(pm_alt_name, ticker_to_name.get(t, ""))
                    if sc > best_score_f1:
                        best_score_f1 = sc; best_tkr_f1 = t
                yes_ticker = best_tkr_f1
            else:
                yes_ticker = best_tkr_f0
        else:
            yes_ticker = best_tkr_f0

        # close_time
        close_ts = ticker_to_close.get(yes_ticker)
        if close_ts is None:
            for t in tickers:
                if t != yes_ticker and t in ticker_to_close:
                    close_ts = ticker_to_close[t]; break
        if close_ts is None:
            ed = fight.get("event_date") or fight.get("pm_fight_date")
            close_ts = (pd.Timestamp(ed).tz_localize("UTC") + pd.Timedelta(hours=30)
                        if ed is not None and pd.notna(ed)
                        else pd.Timestamp.now(tz="UTC"))
            n_fallback += 1

        t_end   = (close_ts - pd.Timedelta(minutes=60)).floor("5min")
        t_start = t_end - pd.Timedelta(hours=WIN_PRE)

        # PM outcome name (only relevant for 2026)
        pm_outcome = (fighters_p[1] if pm_flip and len(fighters_p) >= 2
                      else (fighters_p[0] if fighters_p else ""))

        meta.append({
            "fight_id":     fid,
            "era":          era,
            "event_date":   fight.get("event_date"),
            "pm_id":        str(fight["pm_id"]),
            "yes_ticker":   yes_ticker,
            "pm_flip":      pm_flip,
            "pm_outcome":   pm_outcome,   # 2026 only: which outcome name to filter PM by
            "fighters_pm":  fighters_p,
            "fighters_k":   fight["fighters_kalshi"] or [],
            "t_start":      t_start,
            "t_end":        t_end,
            "close_time":   close_ts,
        })

    print(f"  [{era}] {len(meta)} fights  |  {n_flipped} pm_flip=True  "
          f"| {n_fallback} close_time fallbacks", flush=True)
    if n_flipped:
        for m in meta:
            if m["pm_flip"]:
                print(f"    flip: {m['fight_id']}  yes_ticker={m['yes_ticker']}  "
                      f"pm_outcome={m['pm_outcome']}", flush=True)
    return meta


print("\n[4] building fight meta...", flush=True)
meta25 = build_fight_meta(cw25, ticker_to_name_25, ticker_to_close_25, "2025_lychee")
meta26 = build_fight_meta(cw26, ticker_to_name_26, ticker_to_close_26, "2026_collector")


# =============================================================================
# 5. LOAD KALSHI TRADES — 2025 (Lychee bulk scan)
# =============================================================================
print(f"\n[5] loading Kalshi 2025 trades (Lychee)...", flush=True)
yes_tickers_25 = {m["yes_ticker"] for m in meta25 if m["yes_ticker"]}
yes_arr_25 = pa.array(list(yes_tickers_25), type=pa.string())
trade_files_25 = sorted(K_TRADES_DIR.glob("*.parquet"))
k25_chunks = []
for i, f in enumerate(trade_files_25):
    if i % 1000 == 0 and i > 0:
        print(f"  ... {i}/{len(trade_files_25)} files", flush=True)
    try:
        tbl = pq.read_table(f, columns=["ticker", "yes_price", "count", "created_time"])
        hit = tbl.filter(pc.is_in(tbl.column("ticker"), value_set=yes_arr_25))
        if hit.num_rows > 0:
            k25_chunks.append(hit.to_pandas())
    except Exception:
        continue
k25_all = (pd.concat(k25_chunks, ignore_index=True) if k25_chunks
           else pd.DataFrame(columns=["ticker", "yes_price", "count", "created_time"]))
k25_all["created_time"] = pd.to_datetime(k25_all["created_time"], utc=True)
k25_all["price"]  = k25_all["yes_price"] / 100.0
k25_all["count"]  = pd.to_numeric(k25_all["count"], errors="coerce").fillna(1.0)
k25_all = k25_all.sort_values("created_time").reset_index(drop=True)
print(f"  {len(k25_all):,} rows across {k25_all['ticker'].nunique()} tickers", flush=True)


# =============================================================================
# 6. LOAD PM TRADES — 2025
# =============================================================================
print(f"\n[6] loading PM 2025 trades...", flush=True)
pm25_ids = {m["pm_id"] for m in meta25}
pm25_raw = pd.read_parquet(PM_2025)
pm25_raw["ts_utc"]    = pd.to_datetime(pm25_raw["ts_utc"], utc=True)
pm25_raw["market_id"] = pm25_raw["market_id"].astype(str)
pm25_raw = pm25_raw[pm25_raw["market_id"].isin(pm25_ids)].copy()
pm25_raw = pm25_raw.sort_values("ts_utc").reset_index(drop=True)
# USDC amount: API-sourced rows (post-merge) carry usdc_amount directly;
# legacy Lychee rows derive it from maker/taker amounts via asset-id length heuristic.
_usdc_col = pd.to_numeric(pm25_raw.get("usdc_amount", pd.Series(dtype=float)),
                           errors="coerce")
if _usdc_col.notna().mean() > 0.5:
    pm25_raw["usdc_amount"] = _usdc_col.fillna(0.0)
else:
    pm25_raw["usdc_amount"] = np.where(
        pm25_raw["maker_asset_id"].fillna("").str.len() < 20,
        pm25_raw["maker_amount"],
        pm25_raw["taker_amount"],
    ).astype(float)
print(f"  {len(pm25_raw):,} rows | {pm25_raw['market_id'].nunique()}/{len(pm25_ids)} markets covered",
      flush=True)


# =============================================================================
# 7. LOAD KALSHI TRADES — 2026 (Collector live files)
# =============================================================================
print(f"\n[7] loading Kalshi 2026 trades (Collector live)...", flush=True)
yes_tickers_26 = {m["yes_ticker"] for m in meta26 if m["yes_ticker"]}
k26_files = _glob.glob(str(LIVE / "**" / "trades_KXUFCFIGHT*.parquet"), recursive=True)
k26_chunks = []
for fp in k26_files:
    try:
        chunk = pd.read_parquet(fp, columns=["ticker", "created_time",
                                              "yes_price_dollars", "count_fp"])
        chunk["yes_price_dollars"] = pd.to_numeric(chunk["yes_price_dollars"], errors="coerce")
        chunk["count_fp"] = pd.to_numeric(chunk["count_fp"], errors="coerce").fillna(1.0)
        hit = chunk[chunk["ticker"].isin(yes_tickers_26)]
        if not hit.empty:
            k26_chunks.append(hit)
    except Exception:
        continue
k26_all = (pd.concat(k26_chunks, ignore_index=True) if k26_chunks
           else pd.DataFrame(columns=["ticker", "created_time",
                                       "yes_price_dollars", "count_fp"]))
k26_all["created_time"] = pd.to_datetime(k26_all["created_time"], utc=True, errors="coerce")
k26_all = k26_all.dropna(subset=["created_time", "yes_price_dollars"]).copy()
k26_all = k26_all.sort_values("created_time").reset_index(drop=True)
print(f"  {len(k26_all):,} rows across {k26_all['ticker'].nunique()} tickers "
      f"({len(k26_files)} files scanned)", flush=True)


# =============================================================================
# 8. LOAD PM TRADES — 2026
# =============================================================================
print(f"\n[8] loading PM 2026 trades (gap-fill)...", flush=True)
pm26_ids = {m["pm_id"] for m in meta26}
pm26_raw = pd.read_parquet(PM_2026,
                            columns=["condition_id", "timestamp", "price_yes",
                                     "outcome", "usdc_amount"])
pm26_raw["timestamp"]   = pd.to_datetime(pm26_raw["timestamp"], utc=True)
pm26_raw["price_yes"]   = pd.to_numeric(pm26_raw["price_yes"], errors="coerce")
pm26_raw["usdc_amount"] = pd.to_numeric(pm26_raw["usdc_amount"], errors="coerce").fillna(0.0)
pm26_raw = pm26_raw[pm26_raw["condition_id"].isin(pm26_ids)].sort_values("timestamp").reset_index(drop=True)
print(f"  {len(pm26_raw):,} rows | {pm26_raw['condition_id'].nunique()}/{len(pm26_ids)} markets covered",
      flush=True)


# =============================================================================
# 9. BUILD BARS — 2025 era
# =============================================================================
print(f"\n[9] building 5-min bars — 2025_lychee ({len(meta25)} fights)...", flush=True)
panel_chunks = []
skipped      = []

for fm in meta25:
    fid = fm["fight_id"]
    tkr = fm["yes_ticker"]
    t_s = fm["t_start"]; t_e = fm["t_end"]

    k_raw  = k25_all[k25_all["ticker"] == tkr]
    pm_raw = pm25_raw[pm25_raw["market_id"] == fm["pm_id"]].copy()
    if fm["pm_flip"]:
        pm_raw["price_yes"] = 1.0 - pm_raw["price_yes"]

    kb  = make_bars(k_raw,  "created_time", "price",     "count",       t_s, t_e)
    pmb = make_bars(pm_raw, "ts_utc",       "price_yes", "usdc_amount", t_s, t_e)

    if kb.empty and pmb.empty:
        skipped.append((fid, "zero trades both venues")); continue
    if kb.empty:
        skipped.append((fid, "zero Kalshi trades")); continue
    if pmb.empty:
        skipped.append((fid, "zero PM trades")); continue

    panel_chunks.append(assemble_bars(fid, "2025_lychee", t_s, t_e, kb, pmb))

print(f"  Built: {len(panel_chunks)}  |  Skipped: {len(skipped)}", flush=True)
for fid, reason in skipped:
    print(f"    SKIP {fid}: {reason}", flush=True)


# =============================================================================
# 10. BUILD BARS — 2026 era
# =============================================================================
print(f"\n[10] building 5-min bars — 2026_collector ({len(meta26)} fights)...", flush=True)
skipped26 = []

for fm in meta26:
    fid = fm["fight_id"]
    tkr = fm["yes_ticker"]
    t_s = fm["t_start"]; t_e = fm["t_end"]

    k_raw = k26_all[k26_all["ticker"] == tkr]

    # 2026 PM: filter by condition_id AND outcome (fighter name)
    pm_cid = pm26_raw[pm26_raw["condition_id"] == fm["pm_id"]]
    if not pm_cid.empty and fm["pm_outcome"]:
        pm_raw = pm_cid[pm_cid["outcome"] == fm["pm_outcome"]].copy()
        if pm_raw.empty:
            # Fallback: case-insensitive
            oc_lower = fm["pm_outcome"].lower()
            pm_raw = pm_cid[pm_cid["outcome"].str.lower() == oc_lower].copy()
    else:
        pm_raw = pm_cid.copy()  # no outcome filter if name unavailable

    kb  = make_bars(k_raw,  "created_time",     "yes_price_dollars", "count_fp",   t_s, t_e)
    pmb = make_bars(pm_raw, "timestamp",         "price_yes",         "usdc_amount", t_s, t_e)

    if kb.empty and pmb.empty:
        skipped26.append((fid, "zero trades both venues")); continue
    if kb.empty:
        skipped26.append((fid, "zero Kalshi trades")); continue
    if pmb.empty:
        skipped26.append((fid, "zero PM trades")); continue

    panel_chunks.append(assemble_bars(fid, "2026_collector", t_s, t_e, kb, pmb))

print(f"  Built: {len(panel_chunks) - (len(panel_chunks)-len(skipped26))}... "
      f"total so far {len(panel_chunks)}  |  Skipped: {len(skipped26)}", flush=True)
for fid, reason in skipped26:
    print(f"    SKIP {fid}: {reason}", flush=True)


# =============================================================================
# 11. ASSEMBLE & SAVE PANEL
# =============================================================================
if not panel_chunks:
    sys.exit("ERROR: no fight bars built")

panel = pd.concat(panel_chunks, ignore_index=True)
col_order = [
    "fight_id", "era", "bar_utc",
    "k_last", "k_vwap", "k_n", "k_vol", "k_stale",
    "pm_last", "pm_vwap", "pm_n", "pm_vol", "pm_stale",
    "both_traded",
]
panel = panel[col_order]
panel.to_parquet(OUT_PANEL, index=False)
print(f"\n[11] saved {OUT_PANEL}")
print(f"  {len(panel):,} bars  |  {panel['fight_id'].nunique()} fights")
print(f"  era breakdown:")
for era, grp in panel.groupby("era"):
    print(f"    {era}: {grp['fight_id'].nunique()} fights, {len(grp):,} bars")


# =============================================================================
# 12. PANEL-WIDE SIDE AUDIT
# =============================================================================
print("\n[12] panel-wide side audit...", flush=True)
MIN_CO_BARS = 20
MAD_THRESH  = 0.10

co_bars = panel[panel["both_traded"] & panel["k_last"].notna() & panel["pm_last"].notna()].copy()
fight_co_counts = co_bars.groupby("fight_id").size()
eligible = fight_co_counts[fight_co_counts >= MIN_CO_BARS].index

audit_rows = []
flags      = []

for fid in sorted(eligible):
    sub  = co_bars[co_bars["fight_id"] == fid]
    era  = sub["era"].iloc[0]
    k    = sub["k_last"].values
    pm   = sub["pm_last"].values
    mad_orig = float(np.abs(k - pm).mean())
    mad_flip = float(np.abs(k - (1 - pm)).mean())
    flagged  = (mad_flip < mad_orig) and (mad_orig > MAD_THRESH)

    # pm_flip status for this fight
    all_meta = meta25 + meta26
    fm_match = next((m for m in all_meta if m["fight_id"] == fid), None)
    pm_flip_used = fm_match["pm_flip"] if fm_match else "?"
    pm_outcome_used = fm_match["pm_outcome"] if fm_match else "?"

    audit_rows.append({
        "fight_id":      fid,
        "era":           era,
        "n_co_bars":     len(sub),
        "mad_orig":      round(mad_orig, 4),
        "mad_flip":      round(mad_flip, 4),
        "pm_flip_used":  pm_flip_used,
        "pm_outcome":    pm_outcome_used,
        "flag":          flagged,
    })
    if flagged:
        flags.append(fid)
        print(f"  *** FLAG {fid} [{era}]  MAD_orig={mad_orig:.3f}  MAD_flip={mad_flip:.3f}  "
              f"pm_flip={pm_flip_used}  outcome={pm_outcome_used}", flush=True)

audit_df = pd.DataFrame(audit_rows)
n_eligible = len(eligible)
n_flagged  = len(flags)

print(f"\n  Eligible fights (>= {MIN_CO_BARS} co-active bars): {n_eligible}", flush=True)
print(f"  Flagged: {n_flagged}", flush=True)

# Print full table for review
print(f"\n  {'fight_id':<22} {'era':<18} {'co':>4} {'MAD_o':>6} {'MAD_f':>6} "
      f"{'flip':>5} {'flag':>5}")
print("  " + "-" * 75)
for r in audit_rows:
    flag_str = "***" if r["flag"] else ""
    print(f"  {r['fight_id']:<22} {r['era']:<18} {r['n_co_bars']:>4} "
          f"{r['mad_orig']:>6.3f} {r['mad_flip']:>6.3f} {str(r['pm_flip_used']):>5} "
          f"{flag_str:>5}", flush=True)

# Save audit
audit_lines = [
    "# Phase 2 Combined Panel — Side Audit",
    f"Run: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}",
    f"Threshold: MAD_orig > {MAD_THRESH}  AND  MAD_flip < MAD_orig  → flag",
    f"Min co-active bars: {MIN_CO_BARS}",
    "",
    f"Eligible fights: {n_eligible}  |  Flagged: {n_flagged}",
    "",
    "| fight_id | era | n_co | MAD_orig | MAD_flip | pm_flip | flag |",
    "|:---------|:----|-----:|---------:|---------:|:--------|:-----|",
]
for r in audit_rows:
    flag_str = "FLAG" if r["flag"] else ""
    audit_lines.append(
        f"| {r['fight_id']} | {r['era']} | {r['n_co_bars']} | "
        f"{r['mad_orig']:.4f} | {r['mad_flip']:.4f} | {r['pm_flip_used']} | {flag_str} |"
    )
OUT_AUDIT.write_text("\n".join(audit_lines), encoding="utf-8")
print(f"\n  Audit -> {OUT_AUDIT}", flush=True)

if flags:
    print(f"\n*** STOP — {n_flagged} side assignment issues detected. "
          f"Review qa/phase2_side_audit.md before proceeding. ***", flush=True)
    sys.exit(1)

print(f"\nAudit PASSED — no side assignment issues.", flush=True)


# =============================================================================
# 13. COVERAGE TABLE
# =============================================================================
print("\n[13] coverage table...", flush=True)
cov_rows = []
all_meta = meta25 + meta26
fmeta_map = {m["fight_id"]: m for m in all_meta}

for fid, grp in panel.groupby("fight_id"):
    n  = len(grp)
    kb = int((grp["k_n"] > 0).sum())
    pb = int((grp["pm_n"] > 0).sum())
    bb = int(grp["both_traded"].sum())
    pct = 100.0 * bb / n if n else 0.0
    era = grp["era"].iloc[0]
    fm  = fmeta_map.get(fid, {})
    cov_rows.append({
        "fight_id": fid, "era": era, "n_bars": n, "k_bars": kb,
        "pm_bars": pb, "both_bars": bb, "both_pct": pct,
        "k_n_tot": int(grp["k_n"].sum()), "pm_n_tot": int(grp["pm_n"].sum()),
    })
cov = pd.DataFrame(cov_rows).sort_values("both_pct", ascending=False)

n_fights  = len(cov)
n_ge25    = (cov["both_pct"] >= 25).sum()
n_ge10    = (cov["both_pct"] >= 10).sum()
pcts      = cov["both_pct"].values

print(f"\n  Total fights built: {n_fights}")
print(f"  Total bars:         {len(panel):,}")
print(f"  Total co-active:    {int(panel['both_traded'].sum()):,}  ({100*panel['both_traded'].mean():.1f}%)")
print()
print(f"  {'fight_id':<22} {'era':<18} {'k_bars':>6} {'pm_bars':>7} {'both%':>6}  "
      f"{'k_n':>8} {'pm_n':>8}")
print("  " + "-" * 82)

# Highlight MCGHOL explicitly
for _, row in cov.iterrows():
    fid  = row["fight_id"]
    mark = " <-- MCGHOL" if fid == "20260711_MCGHOL" else ""
    print(f"  {fid:<22} {row['era']:<18} {row['k_bars']:>6} {row['pm_bars']:>7} "
          f"{row['both_pct']:>5.1f}%  {row['k_n_tot']:>8,} {row['pm_n_tot']:>8,}{mark}")

print()
print(f"  fights both% >= 25%: {n_ge25}")
print(f"  fights both% >= 10%: {n_ge10}")
print(f"  p50 both%: {np.percentile(pcts,50):.1f}%")
print()
print(f"[done] panel -> {OUT_PANEL}")
