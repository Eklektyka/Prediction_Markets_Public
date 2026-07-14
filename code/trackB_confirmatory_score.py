#!/usr/bin/env python3
"""
code/trackB_confirmatory_score.py
===================================
ONE-SHOT confirmatory scoring per osf/trackB_confirmatory_registration.md.

SAMPLE:    Lychee Kalshi UFC trades, Feb-Nov 2025
           C:/Kalshi_data/lychee/extracted/data/kalshi/trades/
CRITERION: Q5-Q1 spread (volume-scaled OFI, lag-1) NEGATIVE AND |t| >= 2
SECONDARY: z-OFI Q5-Q1 spread sign (reported, not criterion)
OUTPUT:    qa/trackB_confirmatory_score.md

DO NOT MODIFY THIS SCRIPT AFTER THE FIRST RUN.

Field mapping (Lychee schema):
  trade_id     -> unique trade ID (dedup key)
  ticker       -> KXUFCFIGHT-YYMMMDD-XXXYYY (market identifier)
  count        -> contracts traded
  yes_price    -> price in CENTS (0-100 scale), filter [5, 95]
  taker_side   -> 'yes' or 'no'  (OFI sign: yes=+count, no=-count)
  created_time -> UTC timestamp

Construction rules identical to code/phase1_quintile_sort.py EXCEPT:
  - Data source: Lychee parquet files (not data/raw/live)
  - yes_price already in cents; filter [5, 95] (not 0.05/0.95)
  - MIN_TRADES = 50 (registration specifies 50, not 100)
  - t_end per ticker: (close_time - 60min).floor('5min') -- explicit cutoff
  - Lag-1 only scored (per registration)
"""
from __future__ import annotations
import io, math, re, sys, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.compute as pc

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT          = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
LYCHEE_TRADES = Path(r"C:\Kalshi_data\lychee\extracted\data\kalshi\trades")
LYCHEE_MKTS   = Path(r"C:\Kalshi_data\lychee\extracted\data\kalshi\markets")
OUT_MD        = ROOT / "qa/trackB_confirmatory_score.md"
OUT_MD.parent.mkdir(parents=True, exist_ok=True)

SERIES        = "KXUFCFIGHT"
BUCKET        = "5min"
MIN_TRADES    = 50
N_QUINTILES   = 5
PRICE_LO      = 5.0    # cents
PRICE_HI      = 95.0   # cents


# =============================================================================
# HELPERS
# =============================================================================

def _fight_id(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0]

def _card_date(ticker: str) -> str:
    """KXUFCFIGHT-25FEB22... -> '2025-02-22'."""
    m = re.search(r"KXUFCFIGHT-(\d{2})([A-Z]{3})(\d{2})", ticker)
    if not m:
        return "unknown"
    yr, mon_str, day = int(m.group(1)), m.group(2), int(m.group(3))
    mon = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
           "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}.get(mon_str, 0)
    return f"20{yr:02d}-{mon:02d}-{day:02d}"

def _npval(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2))


# =============================================================================
# STEP 1: Load Lychee Kalshi UFC trades
# =============================================================================

print("Step 1: Loading Lychee Kalshi UFC trades ...", flush=True)

dataset = ds.dataset(str(LYCHEE_TRADES), format="parquet")
filt = pc.starts_with(ds.field("ticker"), SERIES)
tbl = dataset.to_table(
    filter=filt,
    columns=["trade_id", "ticker", "count", "yes_price", "taker_side", "created_time"]
)
df = tbl.to_pandas()
print(f"  Raw KXUFCFIGHT trades: {len(df):,}", flush=True)

# Convert types
df["created_time"] = pd.to_datetime(df["created_time"], utc=True, errors="coerce")
df["count"]     = pd.to_numeric(df["count"],     errors="coerce")
df["yes_price"] = pd.to_numeric(df["yes_price"], errors="coerce")

# Feb-Nov 2025 date filter
T_START = pd.Timestamp("2025-02-01", tz="UTC")
T_END   = pd.Timestamp("2025-12-01", tz="UTC")
df = df[(df["created_time"] >= T_START) & (df["created_time"] < T_END)]
print(f"  After Feb-Nov 2025 date filter: {len(df):,} trades", flush=True)

# Price, side, dedup filters
df = df[df["taker_side"].isin(["yes", "no"])]
df = df[df["yes_price"].between(PRICE_LO, PRICE_HI)]
df = df.dropna(subset=["count", "yes_price"])
df = df.drop_duplicates("trade_id")
print(f"  After price/side/dedup filter: {len(df):,} trades", flush=True)

df["fight"] = df["ticker"].map(_fight_id)
df["card"]  = df["ticker"].map(_card_date)


# =============================================================================
# STEP 2: Load market close_time
# =============================================================================

print("Step 2: Loading market close_time ...", flush=True)
mkt_ds = ds.dataset(str(LYCHEE_MKTS), format="parquet")
mkt_filt = pc.starts_with(ds.field("ticker"), SERIES)
mkt_tbl = mkt_ds.to_table(
    filter=mkt_filt,
    columns=["ticker", "close_time"]
)
mkt_df = mkt_tbl.to_pandas()
mkt_df["close_time"] = pd.to_datetime(mkt_df["close_time"], utc=True, errors="coerce")
mkt_df = mkt_df.dropna(subset=["close_time"])
# Keep latest close_time per ticker (in case of duplicate market snapshots)
mkt_df = mkt_df.sort_values("close_time").drop_duplicates("ticker", keep="last")
# t_end = (close_time - 60min).floor("5min")
mkt_df["t_end"] = (mkt_df["close_time"] - pd.Timedelta("60min")).dt.floor("5min")
print(f"  {len(mkt_df)} markets with close_time", flush=True)


# =============================================================================
# STEP 3: MIN_TRADES filter (on raw trade count, before t_end cutoff)
# =============================================================================

print("Step 3: MIN_TRADES >= {} filter ...".format(MIN_TRADES), flush=True)
tc = df.groupby("ticker")["trade_id"].size()
keep = tc[tc >= MIN_TRADES].index
df = df[df["ticker"].isin(keep)].copy()
n_trades_after_filters = len(df)
n_mkts_raw = len(keep)
print(f"  {n_trades_after_filters:,} trades in {n_mkts_raw} markets", flush=True)


# =============================================================================
# STEP 4: Bucketize (identical construction to phase1_quintile_sort.py)
# =============================================================================

print("Step 4: Bucketizing ...", flush=True)
df = df.sort_values("created_time").reset_index(drop=True)
df["signed"] = np.where(df["taker_side"] == "yes", df["count"], -df["count"])
df["bucket"] = df["created_time"].dt.floor(BUCKET)

b = (df.groupby(["fight","card","ticker","bucket"])
       .agg(ofi         = ("signed",    "sum"),
            total_count = ("count",     "sum"),
            last_price  = ("yes_price", "last"),
            n           = ("trade_id",  "size"))
       .reset_index()
       .sort_values(["ticker","bucket"])
       .reset_index(drop=True))

# Lag-1 forward return: close(t+1) - close(t)
lp = b.groupby("ticker")["last_price"]
b["dp_1"] = lp.shift(-1) - b["last_price"]

print(f"  {len(b):,} bars across {b['ticker'].nunique()} markets (pre t_end)", flush=True)


# =============================================================================
# STEP 5: Apply t_end cutoff per ticker
# =============================================================================

print("Step 5: Applying t_end cutoff per ticker ...", flush=True)
b = b.merge(mkt_df[["ticker","t_end"]], on="ticker", how="left")

no_tend = b[b["t_end"].isna()]["ticker"].unique()
if len(no_tend) > 0:
    print(f"  WARNING: {len(no_tend)} tickers missing close_time, dropping: {list(no_tend[:5])}", flush=True)
    b = b[b["t_end"].notna()].copy()

b = b[b["bucket"] <= b["t_end"]].copy()
b = b.drop(columns=["t_end"])
print(f"  {len(b):,} bars after t_end cutoff ({b['ticker'].nunique()} markets)", flush=True)


# =============================================================================
# STEP 6: Rolling 6-hour volume (identical to phase1_quintile_sort.py)
# =============================================================================

print("Step 6: Rolling 6-hour volume ...", flush=True)
parts = []
for ticker, grp in b.groupby("ticker", sort=False):
    g = grp.set_index("bucket").sort_index()
    g["vol_6h"] = g["total_count"].rolling("360min", min_periods=1).sum()
    parts.append(g.reset_index())
b = pd.concat(parts, ignore_index=True)


# =============================================================================
# STEP 7: OFI variants (identical to phase1_quintile_sort.py)
# =============================================================================

print("Step 7: OFI variants ...", flush=True)
stats = (b.groupby("ticker")["ofi"]
          .agg(ofi_mean="mean", ofi_sd="std")
          .reset_index())
zero_sd = stats.loc[stats["ofi_sd"] == 0, "ticker"].tolist()
if zero_sd:
    print(f"  Dropping {len(zero_sd)} markets with ofi_sd=0", flush=True)
    b = b[~b["ticker"].isin(zero_sd)].copy()
    stats = stats[~stats["ticker"].isin(zero_sd)]

b = b.merge(stats, on="ticker", how="left")
b["ofi_z"]   = (b["ofi"] - b["ofi_mean"]) / b["ofi_sd"]
b["ofi_vol"] = np.where(b["vol_6h"] > 0, b["ofi"] / b["vol_6h"], np.nan)
b = b.drop(columns=["ofi_mean", "ofi_sd"])

n_valid_vol = b["ofi_vol"].notna().sum()
n_valid_z   = b["ofi_z"].notna().sum()
print(f"  Bars with valid ofi_vol: {n_valid_vol:,}  ofi_z: {n_valid_z:,}", flush=True)


# =============================================================================
# STEP 8: ONE-SHOT quintile sort — volume-scaled OFI (PRIMARY)
# =============================================================================

print("Step 8: ONE-SHOT quintile sort (PRIMARY: volume-scaled OFI) ...", flush=True)

def quintile_spread(b: pd.DataFrame, ofi_col: str) -> dict:
    """Q5-Q1 spread on dp_1 with card-clustered SE (identical to phase1)."""
    valid = b.dropna(subset=[ofi_col, "dp_1"]).copy()
    valid["_q"] = pd.qcut(valid[ofi_col], N_QUINTILES,
                          labels=[f"Q{i}" for i in range(1, N_QUINTILES+1)])
    qmeans_dp  = valid.groupby("_q", observed=True)["dp_1"].mean() * 100   # cents
    qmeans_ofi = valid.groupby("_q", observed=True)[ofi_col].mean()

    # Card-clustered SE: per-card Q5-Q1 spread, std(ddof=1)/sqrt(n_cards)
    cq    = valid.groupby(["card","_q"], observed=True)["dp_1"].mean() * 100
    wide  = cq.unstack("_q")[["Q1","Q5"]].dropna()
    spreads = wide["Q5"] - wide["Q1"]
    mu  = float(spreads.mean())
    se  = float(spreads.std(ddof=1)) / math.sqrt(len(spreads)) if len(spreads) >= 2 else np.nan
    t   = mu / se if (se is not None and not np.isnan(se) and se > 0) else np.nan
    p   = _npval(t) if not np.isnan(t) else np.nan
    return dict(
        spread=mu, se=se, t=t, pval=p,
        n_cards=len(wide), n_bars=len(valid),
        qmeans_dp=qmeans_dp.to_dict(),
        qmeans_ofi=qmeans_ofi.to_dict(),
    )

r_vol = quintile_spread(b, "ofi_vol")
r_z   = quintile_spread(b, "ofi_z")

# =============================================================================
# VERDICT
# =============================================================================

spread_vol = r_vol["spread"]
t_vol      = r_vol["t"]
spread_z   = r_z["spread"]

confirm = (spread_vol < 0) and (not np.isnan(t_vol)) and (abs(t_vol) >= 2.0)
verdict = "CONFIRM" if confirm else "FAIL"

print(f"\n{'='*60}", flush=True)
print(f"VERDICT: {verdict}", flush=True)
print(f"  ofi_vol Q5-Q1 spread (lag-1): {spread_vol:+.4f} ct  t={t_vol:+.2f}  p={r_vol['pval']:.4f}", flush=True)
print(f"  ofi_z   Q5-Q1 spread (lag-1): {spread_z:+.4f} ct  t={r_z['t']:+.2f}  (secondary)", flush=True)
print(f"  n_cards={r_vol['n_cards']}  n_bars={r_vol['n_bars']:,}", flush=True)
print(f"{'='*60}", flush=True)

# =============================================================================
# WRITE REPORT
# =============================================================================

now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

vol_rows = ""
for q in [f"Q{i}" for i in range(1, 6)]:
    ofi_m = r_vol["qmeans_ofi"].get(q, float("nan"))
    dp_m  = r_vol["qmeans_dp"].get(q, float("nan"))
    vol_rows += f"| {q} | {ofi_m:.4f} | {dp_m:+.4f} |\n"

z_rows = ""
for q in [f"Q{i}" for i in range(1, 6)]:
    ofi_m = r_z["qmeans_ofi"].get(q, float("nan"))
    dp_m  = r_z["qmeans_dp"].get(q, float("nan"))
    z_rows += f"| {q} | {ofi_m:.4f} | {dp_m:+.4f} |\n"

md_text = f"""# Track B Confirmatory Score
**Generated:** {now}
**Registration:** `osf/trackB_confirmatory_registration.md`
**ONE LOOK — do not re-run or modify after first execution.**

---

## Verdict

# {verdict}

| Metric | Value |
|:-------|------:|
| Volume-scaled OFI Q5-Q1 spread (lag-1, cents) | {spread_vol:+.4f} |
| t-statistic (SE clustered by fight card) | {t_vol:+.2f} |
| p-value (two-sided, normal approx.) | {r_vol["pval"]:.4f} |
| n_cards | {r_vol["n_cards"]} |
| Confirmation criterion | spread < 0 AND |t| ≥ 2 |
| **Verdict** | **{verdict}** |

**Secondary (reported, not criterion):**
- z-OFI Q5-Q1 spread (lag-1): {spread_z:+.4f} ct  (t={r_z["t"]:+.2f})

---

## Sample

| Statistic | Value |
|:----------|------:|
| Trades (KXUFCFIGHT, Feb–Nov 2025, price 5–95¢, ≥{MIN_TRADES} trades, pre-t_end) | {n_trades_after_filters:,} |
| Markets (tickers) after t_end filter | {b["ticker"].nunique()} |
| 5-min bars after t_end filter | {len(b):,} |
| Fight cards | {b["card"].nunique()} |
| Bars with valid ofi_vol | {n_valid_vol:,} |
| t_end rule | (close_time − 60 min).floor("5min") |

---

## Volume-scaled OFI Quintile Sort (PRIMARY)

| Quintile | Mean ofi_vol | Mean dp_lag1 (cents) |
|:--------:|:------------:|:--------------------:|
{vol_rows}
**Q5-Q1 spread:** {spread_vol:+.4f} ct
**SE (card-clustered):** {r_vol["se"]:.4f}
**t:** {t_vol:+.2f}
**p:** {r_vol["pval"]:.4f}
**n_cards:** {r_vol["n_cards"]}
**n_bars:** {r_vol["n_bars"]:,}

---

## z-scored OFI Quintile Sort (SECONDARY — reported, not criterion)

| Quintile | Mean ofi_z | Mean dp_lag1 (cents) |
|:--------:|:----------:|:--------------------:|
{z_rows}
**Q5-Q1 spread:** {spread_z:+.4f} ct
**SE (card-clustered):** {r_z["se"]:.4f}
**t:** {r_z["t"]:+.2f}
**p:** {r_z["pval"]:.4f}
**n_cards:** {r_z["n_cards"]}

---

## Construction Rules

Identical to `code/phase1_quintile_sort.py` except:
- **Data:** Lychee parquet files (`C:/Kalshi_data/lychee/extracted/data/kalshi/trades/`)
- **yes_price:** already in CENTS (0-100); filter applied as `[5, 95]`
- **MIN_TRADES:** 50 (registration specifies 50; Phase 1 used 100)
- **t_end:** `(close_time - 60min).floor("5min")` — bars after t_end excluded
- **Lag scored:** lag-1 only (per registration)
- **OFI sign:** `taker_side='yes'` → +count (positive); `taker_side='no'` → -count
- **vol_6h:** rolling 6h sum of total_count per ticker (window="360min")
- **ofi_vol:** `ofi / vol_6h`; `ofi_z`: within-market z-score (full window)
- **SE clustering:** per-card Q5-Q1 spreads, `std(ddof=1) / sqrt(n_cards)`
"""

OUT_MD.write_text(md_text, encoding="utf-8")
print(f"\nReport written: {OUT_MD}", flush=True)
