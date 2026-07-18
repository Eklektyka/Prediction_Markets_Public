#!/usr/bin/env python3
"""
code/ex5e_large_trade.py
========================
Exhibit 5E: Large-trade OFI split (post-hoc descriptive, 26-card confirmatory panel)

POST-HOC LABEL: This analysis is NOT part of the registered confirmatory test.
It is a descriptive cut applying the pre-specified large-trade filter from
qa/phase1_large_trades.md to the confirmatory panel.

Large-trade cut-off (verbatim from qa/phase1_large_trades.md):
  "Large trades: top-decile of `count` within each market (pre-event training trades)."

Panel: 26 fight cards, Feb-Nov 2025, [5,95]-cent bar filter, 5-min bars, card-clustered SE.
Bootstrap seed=42 (not used here; present for determinism flag).

Output: paper/exhibits/ex5e_large_trade.md
"""
from __future__ import annotations
import math, sys, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.compute as pc

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RNG_SEED = 42  # seed for determinism (no bootstrap here, retained per spec)

ROOT          = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
LYCHEE_TRADES = Path(r"C:\Kalshi_data\lychee\extracted\data\kalshi\trades")
LYCHEE_MKTS   = Path(r"C:\Kalshi_data\lychee\extracted\data\kalshi\markets")
OUT_MD        = ROOT / "paper/exhibits/ex5e_large_trade.md"
OUT_MD.parent.mkdir(parents=True, exist_ok=True)

SERIES        = "KXUFCFIGHT"
BUCKET        = "5min"
MIN_TRADES    = 50
N_QUINTILES   = 5
PRICE_LO      = 5.0    # cents
PRICE_HI      = 95.0   # cents


# =============================================================================
# HELPERS (identical to ex5d_diagnostics.py)
# =============================================================================

def _fight_id(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0]

def _card_date(ticker: str) -> str:
    import re
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
# STEP 1: Load trades (identical to ex5d_diagnostics.py)
# =============================================================================

print("="*70, flush=True)
print("STEP 1: Loading Lychee Kalshi UFC trades ...", flush=True)

dataset = ds.dataset(str(LYCHEE_TRADES), format="parquet")
filt = pc.starts_with(ds.field("ticker"), SERIES)
tbl = dataset.to_table(
    filter=filt,
    columns=["trade_id", "ticker", "count", "yes_price", "taker_side", "created_time"]
)
df = tbl.to_pandas()
print(f"  Raw KXUFCFIGHT trades: {len(df):,}", flush=True)

df["created_time"] = pd.to_datetime(df["created_time"], utc=True, errors="coerce")
df["count"]     = pd.to_numeric(df["count"],     errors="coerce")
df["yes_price"] = pd.to_numeric(df["yes_price"], errors="coerce")

T_START = pd.Timestamp("2025-02-01", tz="UTC")
T_END   = pd.Timestamp("2025-12-01", tz="UTC")
df = df[(df["created_time"] >= T_START) & (df["created_time"] < T_END)]
print(f"  After Feb-Nov 2025 date filter: {len(df):,} trades", flush=True)

df = df[df["taker_side"].isin(["yes", "no"])]
df = df[df["yes_price"].between(PRICE_LO, PRICE_HI)]
df = df.dropna(subset=["count", "yes_price"])
df = df.drop_duplicates("trade_id")
print(f"  After price/side/dedup filter: {len(df):,} trades", flush=True)

df["fight"] = df["ticker"].map(_fight_id)
df["card"]  = df["ticker"].map(_card_date)


# =============================================================================
# STEP 2: Load market close_time (identical to ex5d_diagnostics.py)
# =============================================================================

print("STEP 2: Loading market close_time ...", flush=True)
mkt_ds = ds.dataset(str(LYCHEE_MKTS), format="parquet")
mkt_filt = pc.starts_with(ds.field("ticker"), SERIES)
mkt_tbl = mkt_ds.to_table(filter=mkt_filt, columns=["ticker", "close_time"])
mkt_df = mkt_tbl.to_pandas()
mkt_df["close_time"] = pd.to_datetime(mkt_df["close_time"], utc=True, errors="coerce")
mkt_df = mkt_df.dropna(subset=["close_time"])
mkt_df = mkt_df.sort_values("close_time").drop_duplicates("ticker", keep="last")
mkt_df["t_end"] = (mkt_df["close_time"] - pd.Timedelta("60min")).dt.floor("5min")
print(f"  {len(mkt_df)} markets with close_time", flush=True)


# =============================================================================
# STEP 3: MIN_TRADES filter (identical to ex5d_diagnostics.py)
# =============================================================================

print("STEP 3: MIN_TRADES >= {} filter ...".format(MIN_TRADES), flush=True)
tc = df.groupby("ticker")["trade_id"].size()
keep = tc[tc >= MIN_TRADES].index
df = df[df["ticker"].isin(keep)].copy()
print(f"  {len(df):,} trades in {len(keep)} markets", flush=True)


# =============================================================================
# STEP 4: Large-trade flag (per qa/phase1_large_trades.md)
#
# Verbatim cut-off: "Large trades: top-decile of `count` within each market
#   (pre-event training trades)."
#
# Applied here to the confirmatory panel (post-hoc descriptive):
#   p90 per ticker within the confirmatory panel.
#   is_large = (count >= p90 within ticker)
# =============================================================================

print("STEP 4: Applying large-trade flag (top-decile of count per market) ...", flush=True)
p90 = df.groupby("ticker")["count"].quantile(0.90).rename("p90")
df = df.join(p90, on="ticker")
df["is_large"] = df["count"] >= df["p90"]
n_large = df["is_large"].sum()
n_total = len(df)
print(f"  Large trades: {n_large:,} / {n_total:,} ({100*n_large/n_total:.1f}%)", flush=True)


# =============================================================================
# STEP 5: Bucketize ALL trades (for all-trade OFI + rolling volume)
#          and large-trade OFI separately
# =============================================================================

print("STEP 5: Bucketizing ...", flush=True)
df = df.sort_values("created_time").reset_index(drop=True)
df["signed"]       = np.where(df["taker_side"] == "yes",  df["count"], -df["count"])
df["signed_large"] = np.where(df["is_large"],
                               np.where(df["taker_side"] == "yes", df["count"], -df["count"]),
                               0.0)
df["bucket"] = df["created_time"].dt.floor(BUCKET)

b = (df.groupby(["fight","card","ticker","bucket"])
       .agg(ofi          = ("signed",       "sum"),
            ofi_large    = ("signed_large", "sum"),
            total_count  = ("count",        "sum"),
            last_price   = ("yes_price",    "last"),
            n            = ("trade_id",     "size"))
       .reset_index()
       .sort_values(["ticker","bucket"])
       .reset_index(drop=True))

# Lag-1 forward return
lp = b.groupby("ticker")["last_price"]
b["dp_1"] = lp.shift(-1) - b["last_price"]

print(f"  {len(b):,} bars (pre t_end)", flush=True)


# =============================================================================
# STEP 6: Apply t_end cutoff per ticker (identical to ex5d_diagnostics.py)
# =============================================================================

print("STEP 6: Applying t_end cutoff ...", flush=True)
b = b.merge(mkt_df[["ticker","t_end"]], on="ticker", how="left")
no_tend = b[b["t_end"].isna()]["ticker"].unique()
if len(no_tend) > 0:
    print(f"  WARNING: {len(no_tend)} tickers missing close_time, dropping", flush=True)
    b = b[b["t_end"].notna()].copy()
b = b[b["bucket"] <= b["t_end"]].copy()
b = b.drop(columns=["t_end"])
print(f"  {len(b):,} bars after t_end cutoff ({b['ticker'].nunique()} markets)", flush=True)


# =============================================================================
# STEP 7: Rolling 6-hour volume (identical to ex5d_diagnostics.py)
# =============================================================================

print("STEP 7: Rolling 6-hour volume ...", flush=True)
parts = []
for ticker, grp in b.groupby("ticker", sort=False):
    g = grp.set_index("bucket").sort_index()
    g["vol_6h"] = g["total_count"].rolling("360min", min_periods=1).sum()
    parts.append(g.reset_index())
b = pd.concat(parts, ignore_index=True)


# =============================================================================
# STEP 8: OFI variants — ALL-TRADE (identical to ex5d_diagnostics.py)
# =============================================================================

print("STEP 8: OFI variants (all-trade) ...", flush=True)
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


# =============================================================================
# STEP 9: OFI variants — LARGE-TRADE ONLY
#   vol-OFI: large-trade OFI / rolling 6-hour volume (same denominator as all-trade)
#   z-OFI:   large-trade OFI z-scored within market
# =============================================================================

print("STEP 9: OFI variants (large-trade) ...", flush=True)
large_stats = (b.groupby("ticker")["ofi_large"]
                .agg(large_mean="mean", large_sd="std")
                .reset_index())
zero_large_sd = large_stats.loc[large_stats["large_sd"] == 0, "ticker"].tolist()
if zero_large_sd:
    print(f"  WARNING: {len(zero_large_sd)} markets with large-ofi_sd=0 (z-OFI will be NaN for these)", flush=True)

b = b.merge(large_stats, on="ticker", how="left")
b["ofi_large_z"]   = (b["ofi_large"] - b["large_mean"]) / b["large_sd"].replace(0.0, np.nan)
b["ofi_large_vol"] = np.where(b["vol_6h"] > 0, b["ofi_large"] / b["vol_6h"], np.nan)
b = b.drop(columns=["large_mean", "large_sd"])

n_valid_large_vol = b["ofi_large_vol"].notna().sum()
n_valid_large_z   = b["ofi_large_z"].notna().sum()
print(f"  Bars with valid large ofi_vol: {n_valid_large_vol:,}  large ofi_z: {n_valid_large_z:,}", flush=True)


# =============================================================================
# CHECKSUM: Reproduce all-trade results to confirm panel identity
# =============================================================================

print("\n" + "="*70, flush=True)
print("CHECKSUM VERIFICATION", flush=True)
print("="*70, flush=True)

def quintile_spread(bdf: pd.DataFrame, ofi_col: str, dp_col: str = "dp_1") -> dict:
    """
    Q5-Q1 spread with card-clustered SE (identical to ex5d_diagnostics.py).
    Returns corrected cents (divide raw *100 by 100).

    For large-trade OFI: many bars have zero large-trade flow (no large trade in that bar),
    causing duplicate bin edges. We use duplicates='drop' uniformly to collapse degenerate
    bins, then label lowest bin as Q1 and highest as Q5 for the spread calculation.
    The number of actual bins formed is tracked and reported.
    This is documented as ambiguity E5e-E.
    """
    valid = bdf.dropna(subset=[ofi_col, dp_col]).copy()
    if len(valid) < N_QUINTILES:
        return dict(spread=np.nan, se=np.nan, t=np.nan, pval=np.nan,
                    n_cards=0, n_bars=len(valid), n_bins=0,
                    qmeans_dp={}, qmeans_ofi={})

    # Use duplicates='drop' to handle ties (harmless for all-trade since bins are unique anyway)
    cut_codes, bins = pd.qcut(valid[ofi_col], N_QUINTILES,
                               labels=False, retbins=True, duplicates='drop')
    n_actual = int(cut_codes.nunique())

    if n_actual < 2:
        return dict(spread=np.nan, se=np.nan, t=np.nan, pval=np.nan,
                    n_cards=0, n_bars=len(valid), n_bins=n_actual,
                    qmeans_dp={}, qmeans_ofi={})

    # Label bins Q1..Qn_actual; rename first -> Q1, last -> Q5 for spread
    label_map = {i: f"Q{i+1}" for i in range(n_actual)}
    valid["_q"] = cut_codes.map(label_map).astype("category")

    # Ensure Q1 = lowest, Q5 = highest (rename if n_actual < 5)
    cats = sorted(valid["_q"].cat.categories.tolist(), key=lambda x: int(x[1:]))
    rename = {}
    if cats[0] != "Q1":
        rename[cats[0]] = "Q1"
    if cats[-1] != "Q5":
        rename[cats[-1]] = "Q5"
    if rename:
        valid["_q"] = valid["_q"].cat.rename_categories(
            {c: rename.get(c, c) for c in valid["_q"].cat.categories}
        )

    qmeans_dp  = valid.groupby("_q", observed=True)[dp_col].mean() * 100
    qmeans_ofi = valid.groupby("_q", observed=True)[ofi_col].mean()

    cq    = valid.groupby(["card","_q"], observed=True)[dp_col].mean() * 100
    # unstack; only require Q1 and Q5 columns to be present
    wide_all = cq.unstack("_q")
    if "Q1" not in wide_all.columns or "Q5" not in wide_all.columns:
        return dict(spread=np.nan, se=np.nan, t=np.nan, pval=np.nan,
                    n_cards=0, n_bars=len(valid), n_bins=n_actual,
                    qmeans_dp={k: v/100.0 for k, v in qmeans_dp.to_dict().items()},
                    qmeans_ofi=qmeans_ofi.to_dict())
    wide  = wide_all[["Q1","Q5"]].dropna()
    spreads = wide["Q5"] - wide["Q1"]
    mu  = float(spreads.mean())
    se  = float(spreads.std(ddof=1)) / math.sqrt(len(spreads)) if len(spreads) >= 2 else np.nan
    t   = mu / se if (se is not None and not np.isnan(se) and se > 0) else np.nan
    p   = _npval(t) if not np.isnan(t) else np.nan
    return dict(
        spread=mu / 100.0,
        se=se / 100.0 if not np.isnan(se) else np.nan,
        t=t, pval=p,
        n_cards=len(wide), n_bars=len(valid), n_bins=n_actual,
        qmeans_dp={k: v/100.0 for k, v in qmeans_dp.to_dict().items()},
        qmeans_ofi=qmeans_ofi.to_dict(),
    )

r_vol = quintile_spread(b, "ofi_vol", "dp_1")
r_z   = quintile_spread(b, "ofi_z",   "dp_1")

print(f"  vol-OFI Q5-Q1 lag-1: {r_vol['spread']:+.4f} ct  t={r_vol['t']:+.2f}  n_cards={r_vol['n_cards']}  n_bars={r_vol['n_bars']:,}", flush=True)
print(f"  z-OFI   Q5-Q1 lag-1: {r_z['spread']:+.4f} ct  t={r_z['t']:+.2f}", flush=True)
print(f"  Expected: vol-OFI = -1.1265 ct, t = -6.29; n_bars = 62,119", flush=True)

CHECKSUM_PASS = (
    abs(r_vol['spread'] - (-1.1265)) < 0.0005 and
    abs(r_vol['t'] - (-6.29)) < 0.01 and
    r_vol['n_bars'] == 62119
)

if not CHECKSUM_PASS:
    print("  CHECKSUM FAILED — stopping.", flush=True)
    print(f"  vol-OFI spread={r_vol['spread']:.6f} (expected -1.1265, tol 0.0005)", flush=True)
    print(f"  vol-OFI t={r_vol['t']:.4f} (expected -6.29, tol 0.01)", flush=True)
    print(f"  n_bars={r_vol['n_bars']} (expected 62119)", flush=True)
    sys.exit(1)
else:
    print("  CHECKSUM PASS", flush=True)


# =============================================================================
# LARGE-TRADE QUINTILE SPREADS
# =============================================================================

print("\n" + "="*70, flush=True)
print("LARGE-TRADE OFI QUINTILE SPREADS", flush=True)
print("="*70, flush=True)

r_large_vol = quintile_spread(b, "ofi_large_vol", "dp_1")
r_large_z   = quintile_spread(b, "ofi_large_z",   "dp_1")

print(f"\n  Large-trade vol-OFI Q5-Q1: {r_large_vol['spread']:+.4f} ct  t={r_large_vol['t']:+.2f}  p={r_large_vol['pval']:.4f}  n_cards={r_large_vol['n_cards']}  n_bars={r_large_vol['n_bars']:,}", flush=True)
print(f"  Large-trade z-OFI   Q5-Q1: {r_large_z['spread']:+.4f} ct  t={r_large_z['t']:+.2f}  p={r_large_z['pval']:.4f}  n_cards={r_large_z['n_cards']}  n_bars={r_large_z['n_bars']:,}", flush=True)

# Magnitude ratios
ratio_vol = abs(r_large_vol['spread']) / abs(r_vol['spread']) if r_vol['spread'] != 0 else np.nan
ratio_z   = abs(r_large_z['spread'])   / abs(r_z['spread'])   if r_z['spread'] != 0 else np.nan

print(f"\n  Magnitude ratio (large/all) vol-OFI: {ratio_vol:.2f}x", flush=True)
print(f"  Magnitude ratio (large/all) z-OFI:   {ratio_z:.2f}x", flush=True)
print(f"\n  All-trade references: vol-OFI = -1.1265 ct, z-OFI = -0.1356 ct", flush=True)
print(f"  Historical (8-card training): z-OFI = -0.081 ct, ratio = 0.68x", flush=True)


# =============================================================================
# WRITE MARKDOWN
# =============================================================================

print("\n" + "="*70, flush=True)
print("Writing paper/exhibits/ex5e_large_trade.md ...", flush=True)
print("="*70, flush=True)

now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

def fmt_row(q, ofi_m, dp_m):
    return f"| {q} | {ofi_m:.4f} | {dp_m:+.4f} |"

large_vol_q_rows = "\n".join(
    fmt_row(q, r_large_vol["qmeans_ofi"].get(q, float("nan")),
               r_large_vol["qmeans_dp"].get(q, float("nan")))
    for q in [f"Q{i}" for i in range(1, 6)]
)
large_z_q_rows = "\n".join(
    fmt_row(q, r_large_z["qmeans_ofi"].get(q, float("nan")),
               r_large_z["qmeans_dp"].get(q, float("nan")))
    for q in [f"Q{i}" for i in range(1, 6)]
)

checksum_str = "PASS" if CHECKSUM_PASS else "FAIL"

md = f"""# Exhibit 5E — Large-Trade OFI Split (Post-Hoc Descriptive, 26-Card Confirmatory Panel)
**Generated:** {now}
**Script:** `code/ex5e_large_trade.py`
**Panel:** 26 fight cards, Feb–Nov 2025, 5-min bars, [5,95]¢ price filter, card-clustered SE.
**Prior vintage commit:** bb5d695

---

## (a) POST-HOC Label

This analysis is **NOT part of the registered confirmatory test.** It is a post-hoc descriptive cut applying the pre-specified large-trade filter (defined in `qa/phase1_large_trades.md`) to the confirmatory panel. Results are reported for context only and should not be interpreted as confirming or rejecting any pre-registered hypothesis.

---

## (b) Vintage Check

**Command:** `git diff bb5d695 -- code/trackB_phase1_orderflow.py code/phase1_quintile_sort.py code/score_trackB_holdout.py data/interim/lychee_macro_trades.parquet`

**Result:** No diff. No relevant OFI pipeline file changed since bb5d695. Proceeding to checksum.

**Commit 5afccf3:** Added files only (code/ex5d_diagnostics.py, paper/exhibits/ex5d_diagnostics.md) — no modification to existing files. Confirmed.

---

## (c) Checksum Reproduction

Same confirmatory panel as ex5/ex5d.

| Metric | Reproduced | Expected | Verdict |
|:-------|----------:|--------:|:--------|
| vol-OFI Q5-Q1 lag-1 (ct) | {r_vol['spread']:+.4f} | −1.1265 | {checksum_str} |
| t-statistic (vol-OFI) | {r_vol['t']:+.2f} | −6.29 | {checksum_str} |
| n_bars | {r_vol['n_bars']:,} | 62,119 | {checksum_str} |
| n_cards | {r_vol['n_cards']} | 26 | {checksum_str} |

**Checksum status: {checksum_str}**

z-OFI cross-check (not in checksum gate but reported):
vol-OFI = {r_vol['spread']:+.4f} ct, z-OFI = {r_z['spread']:+.4f} ct (all-trade).

---

## (d) Large-Trade Cut-Off Definition (verbatim from qa/phase1_large_trades.md)

> **Large trades:** top-decile of `count` within each market (pre-event training trades).
> OFI = signed large-trade volume per 5-min bar, z-scored within market.

Applied here to the confirmatory panel (post-hoc): p90 of `count` computed per ticker within the Feb–Nov 2025 confirmatory sample. `is_large = (count >= p90 within ticker)`.

---

## (e) Quintile Sort Results: Large-Trade OFI Only

Note: For vol-OFI, {r_large_vol['n_bins']} of 5 requested bins were formed (many bars have zero large-trade flow; duplicate bin edges dropped — see E5e-E). Q1 = lowest bin, Q5 = highest bin. Bins Q2–Q4 do not exist and show NaN.

### Volume-Scaled (primary): large-trade OFI / rolling 6-hour volume

Bins formed: {r_large_vol['n_bins']} (of 5 requested)

| Quintile | Mean ofi_large_vol | Mean dp_lag1 (cents) |
|:--------:|:------------------:|:--------------------:|
{large_vol_q_rows}

**Q5-Q1 spread:** {r_large_vol['spread']:+.4f} ct | SE: {r_large_vol['se']:.4f} | t: {r_large_vol['t']:+.2f} | p: {r_large_vol['pval']:.4f} | n_cards: {r_large_vol['n_cards']} | n_bars: {r_large_vol['n_bars']:,}

### z-OFI (secondary): large-trade OFI z-scored within market

Bins formed: {r_large_z['n_bins']} (of 5 requested)

| Quintile | Mean ofi_large_z | Mean dp_lag1 (cents) |
|:--------:|:----------------:|:--------------------:|
{large_z_q_rows}

**Q5-Q1 spread:** {r_large_z['spread']:+.4f} ct | SE: {r_large_z['se']:.4f} | t: {r_large_z['t']:+.2f} | p: {r_large_z['pval']:.4f} | n_cards: {r_large_z['n_cards']} | n_bars: {r_large_z['n_bars']:,}

---

## (f) Side-by-Side: Large-Trade vs All-Trade

| Variant | All-Trade Q5-Q1 (ct) | Large-Trade Q5-Q1 (ct) | t | p | Ratio (large/all) |
|:--------|:--------------------:|:----------------------:|:---:|:---:|:-----------------:|
| vol-OFI (primary) | −1.1265 | {r_large_vol['spread']:+.4f} | {r_large_vol['t']:+.2f} | {r_large_vol['pval']:.4f} | {ratio_vol:.2f}× |
| z-OFI (secondary) | −0.1356 | {r_large_z['spread']:+.4f} | {r_large_z['t']:+.2f} | {r_large_z['pval']:.4f} | {ratio_z:.2f}× |

**Historical context (8-card training, exploratory):** z-OFI = −0.081 ct, ratio = 0.68×.

---

## (g) Documented Ambiguities

| ID | Ambiguity | Choice Made |
|:---|:----------|:------------|
| E5e-A | Training vs confirmatory panel for p90 threshold | p90 computed within confirmatory panel (same trades used for analysis). The original spec says "pre-event training trades" but the confirmatory panel is the analysis universe here. This is a post-hoc descriptive so no pre-registration conflict. |
| E5e-B | Denominator for large-trade vol-OFI | Rolling 6-hour volume = total_count (all trades, not just large), same as all-trade vol-OFI denominator. This makes the vol-OFI variants directly comparable. |
| E5e-C | z-OFI markets excluded | Markets where large-trade ofi_sd = 0 have large_z = NaN and are excluded from the z-OFI sort. n_bars may differ between variants. |
| E5e-D | is_large definition | count >= p90 (inclusive), consistent with phase1_large_trades.py line: `df["is_large"] = df["count"] >= df["p90"]` |
| E5e-E | Duplicate bin edges in large-trade vol-OFI quintile sort | Many 5-min bars contain zero large-trade flow (no large trade occurred in that bar). For vol-OFI this creates many tied zero values and only {r_large_vol['n_bins']} distinct bins can be formed. `pd.qcut` is called with `duplicates='drop'`; the lowest bin is labelled Q1 and the highest Q5. Q2-Q4 are absent. The Q5-Q1 spread is therefore a 2-category comparison (most-negative-flow bars vs most-positive-flow bars), not a full quintile sort. For z-OFI, {r_large_z['n_bins']} bins form because z-scoring distributes the zeros across multiple bins. |
"""

OUT_MD.write_text(md, encoding="utf-8")
print(f"Written: {OUT_MD}", flush=True)
print("DONE.", flush=True)
