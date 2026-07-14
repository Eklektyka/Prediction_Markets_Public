"""
SUPERSEDED by code/phase2_combined_panel_build.py — retained for audit trail, do not run.
This script built the 2025-only panel (186 fights). The combined 2025+2026 panel is produced
by phase2_combined_panel_build.py → data/clean/phase2_full_panel.parquet.

phase2_full_panel_build.py
==========================
Build 5-min panel for ALL 186 exact-matched UFC fights.

Identical construction to phase2_panel_build.py (prototype):
  - t_end = Kalshi close_time − 60 min (per fight), floored to 5-min boundary
  - t_start = t_end − 72 h
  - 5-min bars, staleness ffill <= 60 min (12 bars)
  - Post-window bars (t_end .. close_time + 2 h) saved separately

Outputs:
  data/clean/phase2_full_panel.parquet
  data/interim/phase2_full_postwindow_bars.parquet
"""

import json, re, sys, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO   = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
LYCHEE = Path(r"C:\Kalshi_data\lychee\extracted\data")

OUT_CROSSWALK = REPO / "data/meta/ufc_crosswalk.parquet"
PM_TRADES     = REPO / "data/interim/polymarket_ufc_trades.parquet"
OUT_PANEL     = REPO / "data/clean/phase2_full_panel.parquet"
OUT_POSTWIN   = REPO / "data/interim/phase2_full_postwindow_bars.parquet"
OUT_PANEL.parent.mkdir(parents=True, exist_ok=True)
OUT_POSTWIN.parent.mkdir(parents=True, exist_ok=True)

K_MARKETS_DIR = LYCHEE / "kalshi/markets"
K_TRADES_DIR  = LYCHEE / "kalshi/trades"

BAR_FREQ       = "5min"
MAX_FFILL      = 12        # 12 x 5 min = 60 min max staleness
WIN_PRE        = 72        # hours pre-fight
WIN_POST_CLOSE = 2         # hours post-settlement for postwindow file

# ── helpers ───────────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\s]", "", s.lower()).strip()

def name_overlap(a: str, b: str) -> int:
    return len(set(norm(a).split()) & set(norm(b).split()))

# ── 0. Load pm_flip overrides from crosswalk_overrides.csv ───────────────────
OVERRIDES_CSV = REPO / "data/meta/crosswalk_overrides.csv"
overrides_raw = pd.read_csv(OVERRIDES_CSV)
pm_flip_overrides: dict[str, bool] = {}
if "pm_flip_override" in overrides_raw.columns:
    for _, row in overrides_raw.dropna(subset=["pm_flip_override"]).iterrows():
        val = str(row["pm_flip_override"]).strip()
        if val in ("False", "false", "0"):
            pm_flip_overrides[row["fight_id"]] = False
        elif val in ("True", "true", "1"):
            pm_flip_overrides[row["fight_id"]] = True
if pm_flip_overrides:
    print(f"[0] pm_flip_overrides loaded: {pm_flip_overrides}")

# ── 1. Load crosswalk — all 186 exact matches ─────────────────────────────────
print("[1] loading crosswalk...")
cw = pd.read_parquet(OUT_CROSSWALK)
for col in ["fighters_kalshi", "tickers", "fighters_pm", "outcomes", "clob_token_ids"]:
    cw[col] = cw[col].apply(
        lambda x: json.loads(x) if isinstance(x, str) and x else
                  (x if isinstance(x, list) else [])
    )

exact = cw[cw["match_confidence"] == "exact"].copy()
exact["combined_vol"] = exact["kalshi_volume"].fillna(0) + exact["pm_volume"].fillna(0)
exact = exact.sort_values("event_date").reset_index(drop=True)
print(f"  {len(exact)} exact-matched fights")

# ── 2. ticker -> name and ticker -> close_time ────────────────────────────────
print("\n[2] building ticker->name and ticker->close_time maps...")
ticker_to_name:  dict[str, str]           = {}
ticker_to_close: dict[str, pd.Timestamp]  = {}
for f in sorted(K_MARKETS_DIR.glob("*.parquet")):
    df = pd.read_parquet(f, columns=["ticker", "title", "close_time"])
    ufc = df[df["ticker"].str.startswith("KXUFC", na=False)]
    for _, row in ufc.iterrows():
        tkr = row["ticker"]
        m = re.match(r"Will (.+?) win the .+ vs .+ professional MMA", row["title"])
        if m:
            ticker_to_name[tkr] = m.group(1).strip()
        ct = row.get("close_time")
        if ct is not None and pd.notna(ct):
            ts = pd.Timestamp(ct)
            ticker_to_close[tkr] = (ts.tz_localize("UTC") if ts.tzinfo is None
                                    else ts.tz_convert("UTC"))
print(f"  {len(ticker_to_name)} ticker->name  |  {len(ticker_to_close)} ticker->close_time")

# ── 3. YES ticker + PM side + per-fight window ────────────────────────────────
print("\n[3] selecting YES tickers and windows for all 186 fights...")
fight_meta = []
n_flipped = 0
n_fallback = 0

for _, fight in exact.iterrows():
    tickers    = fight["tickers"]
    fighters_p = fight["fighters_pm"] or []
    pm_yes_name = fighters_p[0] if fighters_p else ""

    best_tkr   = tickers[0] if tickers else ""
    best_score = -1
    for t in tickers:
        sc = name_overlap(pm_yes_name, ticker_to_name.get(t, ""))
        if sc > best_score:
            best_score = sc
            best_tkr = t

    fid_key = fight["fight_id"]
    if fid_key in pm_flip_overrides:
        pm_flip = pm_flip_overrides[fid_key]
    else:
        pm_flip = (best_score == 0 and len(tickers) >= 2)
    if pm_flip:
        n_flipped += 1

    close_ts = ticker_to_close.get(best_tkr)
    if close_ts is None:
        for t in tickers:
            if t != best_tkr and t in ticker_to_close:
                close_ts = ticker_to_close[t]; break
    if close_ts is None:
        close_ts = (pd.Timestamp(fight["event_date"]).tz_localize("UTC")
                    + pd.Timedelta(hours=30))
        n_fallback += 1

    t_end   = (close_ts - pd.Timedelta(minutes=60)).floor("5min")
    t_start = t_end - pd.Timedelta(hours=WIN_PRE)

    fight_meta.append({
        "fight_id":   fight["fight_id"],
        "event_date": fight["event_date"],
        "pm_id":      str(fight["pm_id"]),
        "yes_ticker": best_tkr,
        "pm_flip":    pm_flip,
        "fighters_k": fight["fighters_kalshi"],
        "t_start":    t_start,
        "t_end":      t_end,
        "close_time": close_ts,
    })

fmeta = pd.DataFrame(fight_meta)
print(f"  {len(fmeta)} fights  |  {n_flipped} pm_flip=True  |  {n_fallback} close_time fallbacks")
if n_flipped:
    flipped_ids = [m["fight_id"] for m in fight_meta if m["pm_flip"]]
    print(f"  Flipped: {flipped_ids}")
if n_fallback:
    fallback_ids = [m["fight_id"] for m in fight_meta
                    if m["close_time"].hour == 6 and m["close_time"].minute == 0]
    # re-check: fallback close is event_date + 30h
    print(f"  Close_time fallbacks applied to {n_fallback} fights")

# ── 4. Scan Kalshi trades — all YES tickers in one pass ──────────────────────
yes_tickers = set(fmeta["yes_ticker"].dropna().tolist())
yes_arr = pa.array(list(yes_tickers), type=pa.string())
trade_files = sorted(K_TRADES_DIR.glob("*.parquet"))
print(f"\n[4] scanning Kalshi trades: {len(yes_tickers)} tickers across {len(trade_files)} files...")

k_chunks = []
for i, f in enumerate(trade_files):
    if i % 1000 == 0 and i > 0:
        print(f"  ... {i}/{len(trade_files)} files, {sum(len(c) for c in k_chunks):,} rows so far")
    try:
        tbl = pq.read_table(f, columns=["ticker", "yes_price", "count", "created_time"])
        hit = tbl.filter(pc.is_in(tbl.column("ticker"), value_set=yes_arr))
        if hit.num_rows > 0:
            k_chunks.append(hit.to_pandas())
    except Exception:
        continue

k_all = (pd.concat(k_chunks, ignore_index=True) if k_chunks
         else pd.DataFrame(columns=["ticker", "yes_price", "count", "created_time"]))
k_all["created_time"] = pd.to_datetime(k_all["created_time"], utc=True)
k_all["price"] = k_all["yes_price"] / 100.0
k_all["count"] = pd.to_numeric(k_all["count"], errors="coerce").fillna(1).astype(float)
k_all = k_all.sort_values("created_time").reset_index(drop=True)
print(f"  {len(k_all):,} Kalshi trade rows across {k_all['ticker'].nunique()} tickers")

# ── 5. Load PM trades ─────────────────────────────────────────────────────────
print(f"\n[5] loading PM trades from interim file...")
pm_ids_needed = set(fmeta["pm_id"].tolist())
pm_all = pd.read_parquet(PM_TRADES)
pm_all["ts_utc"]    = pd.to_datetime(pm_all["ts_utc"], utc=True)
pm_all["market_id"] = pm_all["market_id"].astype(str)
pm_all = pm_all[pm_all["market_id"].isin(pm_ids_needed)].copy()
pm_all = pm_all.sort_values("ts_utc").reset_index(drop=True)
pm_all["usdc_amount"] = np.where(
    pm_all["maker_asset_id"].str.len() < 20,
    pm_all["maker_amount"],
    pm_all["taker_amount"],
).astype(float)

covered_pm_ids = set(pm_all["market_id"].unique())
missing_pm = pm_ids_needed - covered_pm_ids
print(f"  {len(pm_all):,} PM rows | {len(covered_pm_ids)}/{len(pm_ids_needed)} markets covered "
      f"| {len(missing_pm)} missing")
if missing_pm:
    missing_fids = fmeta[fmeta["pm_id"].isin(missing_pm)]["fight_id"].tolist()
    print(f"  PM-missing fights: {missing_fids}")

# ── 6. Bar construction helpers ───────────────────────────────────────────────
def make_bars(trades_df, time_col, price_col, weight_col, t_start, t_end):
    df = trades_df[
        (trades_df[time_col] >= t_start) & (trades_df[time_col] <= t_end)
    ].copy()
    if df.empty:
        return pd.DataFrame(columns=["last", "vwap", "n", "vol"])
    df["bar"]   = df[time_col].dt.floor(BAR_FREQ)
    df["px_w"]  = df[price_col] * df[weight_col]
    grp = df.groupby("bar", sort=True).agg(
        n       = (price_col, "count"),
        last    = (price_col, "last"),
        sum_pxw = ("px_w",    "sum"),
        vol     = (weight_col, "sum"),
    )
    grp["vwap"] = grp["sum_pxw"] / grp["vol"].replace(0, np.nan)
    return grp[["last", "vwap", "n", "vol"]]

def apply_stale_ffill(s_raw, max_fill):
    s_ff  = s_raw.ffill(limit=max_fill)
    stale = s_raw.isna() & s_ff.notna()
    return s_ff, stale

# ── 7. Build bars per fight ───────────────────────────────────────────────────
print(f"\n[6] building bars for {len(fmeta)} fights...")
panel_chunks  = []
postwin_chunks = []
skipped       = []

for idx, fm in fmeta.iterrows():
    fid        = fm["fight_id"]
    tkr        = fm["yes_ticker"]
    pm_id      = fm["pm_id"]
    t_start    = fm["t_start"]
    t_end      = fm["t_end"]
    close_time = fm["close_time"]
    t_postend  = close_time + pd.Timedelta(hours=WIN_POST_CLOSE)

    k_raw  = k_all[k_all["ticker"] == tkr]
    pm_raw = pm_all[pm_all["market_id"] == pm_id].copy()
    if fm["pm_flip"]:
        pm_raw["price_yes"] = 1.0 - pm_raw["price_yes"]

    kb  = make_bars(k_raw,  "created_time", "price",     "count",       t_start, t_end)
    pmb = make_bars(pm_raw, "ts_utc",       "price_yes", "usdc_amount", t_start, t_end)

    skip_reason = None
    if kb.empty and pmb.empty:
        skip_reason = "zero trades both venues"
    elif kb.empty:
        skip_reason = "zero Kalshi trades"
    elif pmb.empty:
        skip_reason = "zero PM trades"

    if skip_reason:
        skipped.append({"fight_id": fid, "reason": skip_reason})
        print(f"  SKIP {fid}: {skip_reason}")
    else:
        bar_idx = pd.date_range(t_start, t_end, freq=BAR_FREQ, tz="UTC", inclusive="left")
        kb  = kb.reindex(bar_idx)
        pmb = pmb.reindex(bar_idx)

        k_last_ff,  k_stale  = apply_stale_ffill(kb["last"],  MAX_FFILL)
        pm_last_ff, pm_stale = apply_stale_ffill(pmb["last"], MAX_FFILL)

        bars = pd.DataFrame({
            "fight_id": fid,
            "bar_utc":  bar_idx,
            "k_last":   k_last_ff,    "k_vwap":  kb["vwap"],
            "k_n":      kb["n"].fillna(0).astype(int),
            "k_vol":    kb["vol"].fillna(0),
            "k_stale":  k_stale.fillna(False),
            "pm_last":  pm_last_ff,   "pm_vwap": pmb["vwap"],
            "pm_n":     pmb["n"].fillna(0).astype(int),
            "pm_vol":   pmb["vol"].fillna(0),
            "pm_stale": pm_stale.fillna(False),
        })
        bars = bars[bars["k_last"].notna() | bars["pm_last"].notna()].copy()
        bars["both_traded"] = (bars["k_n"] > 0) & (bars["pm_n"] > 0)
        panel_chunks.append(bars)

    # Post-window bars (always attempt, independent of main-window skip)
    kb_pw  = make_bars(k_raw,  "created_time", "price",     "count",       t_end, t_postend)
    pmb_pw = make_bars(pm_raw, "ts_utc",       "price_yes", "usdc_amount", t_end, t_postend)

    if not kb_pw.empty or not pmb_pw.empty:
        pw_idx = pd.date_range(t_end, t_postend, freq=BAR_FREQ, tz="UTC", inclusive="left")
        kb_pw  = kb_pw.reindex(pw_idx)
        pmb_pw = pmb_pw.reindex(pw_idx)
        pw = pd.DataFrame({
            "fight_id": fid, "bar_utc": pw_idx,
            "k_last":   kb_pw["last"],  "k_vwap":  kb_pw["vwap"],
            "k_n":      kb_pw["n"].fillna(0).astype(int),
            "k_vol":    kb_pw["vol"].fillna(0),
            "pm_last":  pmb_pw["last"], "pm_vwap": pmb_pw["vwap"],
            "pm_n":     pmb_pw["n"].fillna(0).astype(int),
            "pm_vol":   pmb_pw["vol"].fillna(0),
        })
        pw = pw[(pw["k_n"] > 0) | (pw["pm_n"] > 0)].copy()
        pw["both_traded"] = (pw["k_n"] > 0) & (pw["pm_n"] > 0)
        if not pw.empty:
            postwin_chunks.append(pw)

# ── 8. Assemble & save ────────────────────────────────────────────────────────
if not panel_chunks:
    sys.exit("ERROR: no fights built")

panel = pd.concat(panel_chunks, ignore_index=True)
col_order = [
    "fight_id", "bar_utc",
    "k_last", "k_vwap", "k_n", "k_vol", "k_stale",
    "pm_last", "pm_vwap", "pm_n", "pm_vol", "pm_stale",
    "both_traded",
]
panel = panel[col_order]
panel.to_parquet(OUT_PANEL, index=False)
print(f"\n[7] saved {OUT_PANEL}  ({len(panel):,} rows, "
      f"{panel['fight_id'].nunique()} fights)")

if postwin_chunks:
    postwin = pd.concat(postwin_chunks, ignore_index=True)
    pw_cols = ["fight_id","bar_utc",
               "k_last","k_vwap","k_n","k_vol",
               "pm_last","pm_vwap","pm_n","pm_vol","both_traded"]
    postwin[[c for c in pw_cols if c in postwin.columns]].to_parquet(OUT_POSTWIN, index=False)
    print(f"    post-window: {OUT_POSTWIN}  ({len(postwin):,} rows, "
          f"{postwin['fight_id'].nunique()} fights)")

# ── 9. Coverage table ─────────────────────────────────────────────────────────
print()
print("=" * 100)
print("PHASE 2 FULL PANEL — COVERAGE")
print("=" * 100)

# per-fight both%
cov_rows = []
for fid, grp in panel.groupby("fight_id"):
    n  = len(grp)
    kb = int((grp["k_n"] > 0).sum())
    pb = int((grp["pm_n"] > 0).sum())
    bb = int(grp["both_traded"].sum())
    pct = 100.0 * bb / n if n else 0.0
    cov_rows.append({"fight_id": fid, "n_bars": n, "k_bars": kb,
                     "pm_bars": pb, "both_bars": bb, "both_pct": pct})

cov = pd.DataFrame(cov_rows).sort_values("both_pct", ascending=False)

n_fights  = len(cov)
n_ge25    = (cov["both_pct"] >= 25).sum()
n_ge10    = (cov["both_pct"] >= 10).sum()
n_ge1     = (cov["both_pct"] >= 1).sum()
n_zero    = (cov["both_pct"] == 0).sum()

pcts = cov["both_pct"].values
print(f"\n  Fights built:      {n_fights} / {len(exact)} exact")
print(f"  Fights skipped:    {len(skipped)}")
print(f"  Total bars:        {len(panel):,}")
print(f"  Total both-traded: {int(panel['both_traded'].sum()):,} / {len(panel):,}"
      f"  ({100*panel['both_traded'].mean():.1f}%)")
print()
print("  both% distribution across fights:")
print(f"    p10  = {np.percentile(pcts, 10):5.1f}%")
print(f"    p25  = {np.percentile(pcts, 25):5.1f}%")
print(f"    p50  = {np.percentile(pcts, 50):5.1f}%")
print(f"    p75  = {np.percentile(pcts, 75):5.1f}%")
print(f"    p90  = {np.percentile(pcts, 90):5.1f}%")
print()
print(f"  Fights with both% >= 25%:  {n_ge25}")
print(f"  Fights with both% >= 10%:  {n_ge10}")
print(f"  Fights with both% >=  1%:  {n_ge1}")
print(f"  Fights with both%  = 0%:   {n_zero}")

print()
print(f"  {'fight_id':<22} {'date':<12} {'k_bars':>6} {'pm_bars':>7} {'both_bars':>10}"
      f" {'both%':>6}  {'k_n_tot':>8} {'pm_n_tot':>9}")
print("  " + "-" * 85)
for _, row in cov.iterrows():
    fid = row["fight_id"]
    fm  = fmeta[fmeta["fight_id"] == fid].iloc[0]
    date_str = str(fm["event_date"].date()) if pd.notna(fm["event_date"]) else "?"
    sub  = panel[panel["fight_id"] == fid]
    kn   = int(sub["k_n"].sum())
    pmn  = int(sub["pm_n"].sum())
    print(f"  {fid:<22} {date_str:<12} {row['k_bars']:>6} {row['pm_bars']:>7}"
          f" {row['both_bars']:>10} {row['both_pct']:>5.1f}%  {kn:>8,} {pmn:>9,}")

if skipped:
    print()
    print("  SKIPPED fights:")
    for s in skipped:
        print(f"    {s['fight_id']}  reason: {s['reason']}")
