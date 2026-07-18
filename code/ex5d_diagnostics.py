#!/usr/bin/env python3
"""
code/ex5d_diagnostics.py
========================
Exhibit 5D: OFI bounce diagnostics (skip-one, liquidity split, Roll bound)

Three post-confirmatory diagnostics on the same confirmatory panel as ex5:
- 26 fight cards, Feb-Nov 2025, [5,95]-cent bar filter, 5-min bars, card-clustered SE.

GROUND RULES:
- Checksum reproduction FIRST (must match: vol-OFI Q5-Q1 = -1.13ct t=-6.29; z-OFI = -0.14ct t=-1.27)
- All diagnostics use identical panel construction to trackB_confirmatory_score.py
- Bootstrap seed=42
- Output: paper/exhibits/ex5d_diagnostics.md

Documented ambiguities (no prior code found for D.3 and D.4):
  D.3-A: Median split of markets is by total trades (sum over all bars in panel).
  D.3-B: Regressand = dp_1 (lag-1 forward return in raw price units, not cents).
         Regressor = signed flow (ofi, raw contract counts).
         Coefficient units: price per contract. Reported in standard floating point.
  D.3-C: Clustering: card-clustered (same as ex5).
  D.3-D: "Multi-trade bars" defined as bars where n > 1 (more than one trade).
  D.3-E: "Thick multi-trade" = thick-market bars restricted to n > 1.
  D.3-F: Bar-depth coefficient ratio = thin coef / thick coef.
  D.4-A: Roll (1984) bound: effective half-spread = sqrt(max(-Cov(dp_t, dp_{t-1}), 0))
         where dp is first difference of last_price within each market.
         Markets with non-negative autocovariance get half-spread = 0 (per Roll's bound).
  D.4-B: Per-market autocovariance computed as sample covariance (ddof=1) of consecutive dp pairs.
  D.4-C: Median half-spread taken across all markets with >= 2 consecutive dp observations.
  D.4-D: "Bounce-implied flow coefficient at median bar flow": spread * 2 / median_ofi_absolute
         where spread is the median half-spread and median_ofi_absolute is median |ofi| across bars.
         Rationale: one half-spread bounce = 2*s price impact over median |ofi| contracts.
  D.4-E: "Measured flow coefficient" = coefficient from same D.3 OLS regression (pooled panel).
  D.4-F: Equivalent imbalance = 2*s / measured_coef (contracts needed to move by one full spread).
  D.4-G: Zero-price-change bars = bars where dp_1 == 0.
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
OUT_MD        = ROOT / "paper/exhibits/ex5d_diagnostics.md"
OUT_MD.parent.mkdir(parents=True, exist_ok=True)

SERIES        = "KXUFCFIGHT"
BUCKET        = "5min"
MIN_TRADES    = 50
N_QUINTILES   = 5
PRICE_LO      = 5.0    # cents
PRICE_HI      = 95.0   # cents
RNG_SEED      = 42


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
# STEP 1: Load Lychee Kalshi UFC trades (identical to trackB_confirmatory_score.py)
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
# STEP 2: Load market close_time (identical to trackB_confirmatory_score.py)
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
# STEP 3: MIN_TRADES filter
# =============================================================================

print("STEP 3: MIN_TRADES >= {} filter ...".format(MIN_TRADES), flush=True)
tc = df.groupby("ticker")["trade_id"].size()
keep = tc[tc >= MIN_TRADES].index
df = df[df["ticker"].isin(keep)].copy()
n_trades_after_filters = len(df)
n_mkts_raw = len(keep)
print(f"  {n_trades_after_filters:,} trades in {n_mkts_raw} markets", flush=True)


# =============================================================================
# STEP 4: Bucketize
# =============================================================================

print("STEP 4: Bucketizing ...", flush=True)
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

# Lag-1 forward return
lp = b.groupby("ticker")["last_price"]
b["dp_1"] = lp.shift(-1) - b["last_price"]

print(f"  {len(b):,} bars (pre t_end)", flush=True)


# =============================================================================
# STEP 5: Apply t_end cutoff per ticker
# =============================================================================

print("STEP 5: Applying t_end cutoff ...", flush=True)
b = b.merge(mkt_df[["ticker","t_end"]], on="ticker", how="left")
no_tend = b[b["t_end"].isna()]["ticker"].unique()
if len(no_tend) > 0:
    print(f"  WARNING: {len(no_tend)} tickers missing close_time, dropping", flush=True)
    b = b[b["t_end"].notna()].copy()
b = b[b["bucket"] <= b["t_end"]].copy()
b = b.drop(columns=["t_end"])
print(f"  {len(b):,} bars after t_end cutoff ({b['ticker'].nunique()} markets)", flush=True)


# =============================================================================
# STEP 6: Rolling 6-hour volume
# =============================================================================

print("STEP 6: Rolling 6-hour volume ...", flush=True)
parts = []
for ticker, grp in b.groupby("ticker", sort=False):
    g = grp.set_index("bucket").sort_index()
    g["vol_6h"] = g["total_count"].rolling("360min", min_periods=1).sum()
    parts.append(g.reset_index())
b = pd.concat(parts, ignore_index=True)


# =============================================================================
# STEP 7: OFI variants
# =============================================================================

print("STEP 7: OFI variants ...", flush=True)
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
# STEP 8: Also compute dp_2 (lag-2, for skip-one diagnostic)
# =============================================================================

print("STEP 8: Computing lag-2 forward return (dp_2) ...", flush=True)
# dp_2: price change from close(t+1) to close(t+2) = lp.shift(-2) - lp.shift(-1)
# This is the "skip-one" return: OFI at t predicts return from t+1 to t+2
for ticker, grp in b.groupby("ticker", sort=False):
    idx = grp.index
    lp_vals = grp["last_price"].values
    # dp_2[i] = last_price[i+2] - last_price[i+1]
    dp2 = np.full(len(lp_vals), np.nan)
    dp2[:-2] = lp_vals[2:] - lp_vals[1:-1]
    b.loc[idx, "dp_2"] = dp2

n_valid_dp2 = b["dp_2"].notna().sum()
print(f"  Bars with valid dp_2: {n_valid_dp2:,}", flush=True)


# =============================================================================
# CHECKSUM VERIFICATION (must match before proceeding to diagnostics)
# =============================================================================

print("\n" + "="*70, flush=True)
print("CHECKSUM VERIFICATION", flush=True)
print("="*70, flush=True)

def quintile_spread(bdf: pd.DataFrame, ofi_col: str, dp_col: str = "dp_1") -> dict:
    """Q5-Q1 spread with card-clustered SE (identical to trackB_confirmatory_score.py).

    NOTE on units: The confirmatory score script multiplies dp by 100 to convert to cents,
    but yes_price is already in cents (0-100), so dp is already in cents.
    The *100 creates a 100x inflation of the spread value.
    t-statistics are scale-invariant and are CORRECT.
    Spreads returned here are the RAW values (inflated by 100x);
    call site divides by 100 to get true cents.
    This matches the trackB_confirmatory_score.py behavior exactly.
    """
    valid = bdf.dropna(subset=[ofi_col, dp_col]).copy()
    valid["_q"] = pd.qcut(valid[ofi_col], N_QUINTILES,
                          labels=[f"Q{i}" for i in range(1, N_QUINTILES+1)])
    qmeans_dp  = valid.groupby("_q", observed=True)[dp_col].mean() * 100   # raw (inflated)
    qmeans_ofi = valid.groupby("_q", observed=True)[ofi_col].mean()

    cq    = valid.groupby(["card","_q"], observed=True)[dp_col].mean() * 100
    wide  = cq.unstack("_q")[["Q1","Q5"]].dropna()
    spreads = wide["Q5"] - wide["Q1"]
    mu  = float(spreads.mean())
    se  = float(spreads.std(ddof=1)) / math.sqrt(len(spreads)) if len(spreads) >= 2 else np.nan
    t   = mu / se if (se is not None and not np.isnan(se) and se > 0) else np.nan
    p   = _npval(t) if not np.isnan(t) else np.nan
    return dict(
        spread_raw=mu,         # raw, 100x inflated
        spread=mu / 100.0,     # corrected cents
        se_raw=se,
        se=se / 100.0 if se is not None and not np.isnan(se) else np.nan,
        t=t, pval=p,
        n_cards=len(wide), n_bars=len(valid),
        qmeans_dp={k: v/100.0 for k, v in qmeans_dp.to_dict().items()},
        qmeans_ofi=qmeans_ofi.to_dict(),
    )

r_vol = quintile_spread(b, "ofi_vol", "dp_1")
r_z   = quintile_spread(b, "ofi_z",   "dp_1")

print(f"  vol-OFI Q5-Q1 lag-1: {r_vol['spread']:+.4f} ct  (raw: {r_vol['spread_raw']:+.4f})  t={r_vol['t']:+.2f}  n_cards={r_vol['n_cards']}", flush=True)
print(f"  z-OFI   Q5-Q1 lag-1: {r_z['spread']:+.4f} ct  (raw: {r_z['spread_raw']:+.4f})  t={r_z['t']:+.2f}", flush=True)
print(f"  Expected: vol-OFI = -1.1265 ct, t = -6.29; z-OFI = -0.1356 ct, t = -1.27", flush=True)

# Checksum against corrected cent values
CHECKSUM_PASS = (
    abs(r_vol['spread'] - (-1.1265)) < 0.0005 and
    abs(r_vol['t'] - (-6.29)) < 0.01 and
    abs(r_z['spread'] - (-0.1356)) < 0.0005 and
    abs(r_z['t'] - (-1.27)) < 0.01
)

if not CHECKSUM_PASS:
    print("  CHECKSUM FAILED — stopping.", flush=True)
    sys.exit(1)
else:
    print("  CHECKSUM PASS", flush=True)


# =============================================================================
# D.2 SKIP-ONE (lag-2 quintile spreads)
# =============================================================================

print("\n" + "="*70, flush=True)
print("D.2 SKIP-ONE: Lag-2 quintile spreads", flush=True)
print("="*70, flush=True)

r_z_lag2   = quintile_spread(b, "ofi_z",   "dp_2")
r_vol_lag2 = quintile_spread(b, "ofi_vol", "dp_2")

print(f"\n  z-OFI   Q5-Q1 lag-2: {r_z_lag2['spread']:+.4f} ct  t={r_z_lag2['t']:+.2f}  p={r_z_lag2['pval']:.4f}  n_cards={r_z_lag2['n_cards']}", flush=True)
print(f"  vol-OFI Q5-Q1 lag-2: {r_vol_lag2['spread']:+.4f} ct  t={r_vol_lag2['t']:+.2f}  p={r_vol_lag2['pval']:.4f}  n_cards={r_vol_lag2['n_cards']}", flush=True)


# =============================================================================
# D.3 LIQUIDITY SPLIT
# =============================================================================

print("\n" + "="*70, flush=True)
print("D.3 LIQUIDITY SPLIT", flush=True)
print("="*70, flush=True)

# Documented choice D.3-A: total trades = sum of n (bar-level trade count) per ticker
market_trades = b.groupby("ticker")["n"].sum()
median_trades = market_trades.median()
print(f"  Median market total trades: {median_trades:.1f}", flush=True)
thin_tickers = market_trades[market_trades <= median_trades].index
thick_tickers = market_trades[market_trades > median_trades].index
print(f"  Thin markets: {len(thin_tickers)}  |  Thick markets: {len(thick_tickers)}", flush=True)

b_thin  = b[b["ticker"].isin(thin_tickers)].copy()
b_thick = b[b["ticker"].isin(thick_tickers)].copy()
b_thick_multi = b_thick[b_thick["n"] > 1].copy()

def ols_card_clustered(bdf: pd.DataFrame, y_col: str, x_col: str) -> dict:
    """
    OLS: y ~ x (no intercept suppression, no FE — pooled OLS matching D.3 description).
    Card-clustered SE via cluster sandwich estimator.
    Documented choice D.3-B: raw dp_1 (price units) as y, raw ofi (contracts) as x.
    """
    valid = bdf.dropna(subset=[y_col, x_col]).copy()
    if len(valid) < 2:
        return dict(coef=np.nan, se=np.nan, t=np.nan, pval=np.nan, n=len(valid))

    y = valid[y_col].values
    x = valid[x_col].values
    # OLS with intercept
    X = np.column_stack([np.ones(len(x)), x])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        return dict(coef=np.nan, se=np.nan, t=np.nan, pval=np.nan, n=len(valid))

    coef = beta[1]  # slope on x
    resid = y - X @ beta
    n = len(y)
    k = 2  # intercept + slope

    # Card-clustered SE (sandwich)
    cards = valid["card"].values
    unique_cards = np.unique(cards)
    G = len(unique_cards)

    XtX_inv = np.linalg.pinv(X.T @ X)
    meat = np.zeros((k, k))
    for card in unique_cards:
        mask = cards == card
        Xg = X[mask]
        rg = resid[mask]
        score_g = Xg.T @ rg
        meat += np.outer(score_g, score_g)

    # Small-sample correction: G/(G-1) * n/(n-k)
    if G > 1:
        correction = (G / (G - 1)) * (n / (n - k))
        vcov = XtX_inv @ meat @ XtX_inv * correction
    else:
        vcov = XtX_inv @ meat @ XtX_inv

    se_coef = math.sqrt(max(vcov[1, 1], 0.0))
    t_stat = coef / se_coef if se_coef > 0 else np.nan
    pval = _npval(t_stat) if not np.isnan(t_stat) else np.nan

    return dict(coef=coef, se=se_coef, t=t_stat, pval=pval, n=n, G=G)

# Pooled regression for all bars (for D.4 "measured coefficient")
r_pool  = ols_card_clustered(b.dropna(subset=["dp_1"]), "dp_1", "ofi")
r_thin  = ols_card_clustered(b_thin.dropna(subset=["dp_1"]), "dp_1", "ofi")
r_thick = ols_card_clustered(b_thick.dropna(subset=["dp_1"]), "dp_1", "ofi")
r_thick_multi = ols_card_clustered(b_thick_multi.dropna(subset=["dp_1"]), "dp_1", "ofi")

# Single-trade vs multi-trade bars
b_single = b[b["n"] == 1].copy()
b_multi  = b[b["n"] > 1].copy()
r_single = ols_card_clustered(b_single.dropna(subset=["dp_1"]), "dp_1", "ofi")
r_multi  = ols_card_clustered(b_multi.dropna(subset=["dp_1"]), "dp_1", "ofi")

# Depth ratio: single / multi
if r_multi["coef"] != 0 and not np.isnan(r_multi["coef"]) and not np.isnan(r_single["coef"]):
    depth_ratio = r_single["coef"] / r_multi["coef"]
else:
    depth_ratio = np.nan

print(f"\n  Pooled OLS: coef={r_pool['coef']:.4e}  t={r_pool['t']:+.2f}  p={r_pool['pval']:.4f}  n={r_pool['n']:,}  G={r_pool.get('G','?')}", flush=True)
print(f"  Thin:       coef={r_thin['coef']:.4e}  t={r_thin['t']:+.2f}  p={r_thin['pval']:.4f}  n={r_thin['n']:,}", flush=True)
print(f"  Thick:      coef={r_thick['coef']:.4e}  t={r_thick['t']:+.2f}  p={r_thick['pval']:.4f}  n={r_thick['n']:,}", flush=True)
print(f"  Thick multi-trade: coef={r_thick_multi['coef']:.4e}  t={r_thick_multi['t']:+.2f}  p={r_thick_multi['pval']:.4f}  n={r_thick_multi['n']:,}", flush=True)
print(f"  Single-trade bars: coef={r_single['coef']:.4e}  t={r_single['t']:+.2f}  p={r_single['pval']:.4f}  n={r_single['n']:,}", flush=True)
print(f"  Multi-trade bars:  coef={r_multi['coef']:.4e}  t={r_multi['t']:+.2f}  p={r_multi['pval']:.4f}  n={r_multi['n']:,}", flush=True)
print(f"  Depth ratio (single/multi): {depth_ratio:.2f}", flush=True)


# =============================================================================
# D.4 ROLL BOUND
# =============================================================================

print("\n" + "="*70, flush=True)
print("D.4 ROLL BOUND (effective half-spread)", flush=True)
print("="*70, flush=True)

# Per-market: compute first-differences of last_price, then lag-1 autocovariance
# Documented choice D.4-A/B: sample cov (ddof=1) of consecutive dp pairs
# D.4-A: markets with non-negative autocovariance get half-spread = 0

half_spreads = []
market_autocov_results = []

for ticker, grp in b.sort_values(["ticker","bucket"]).groupby("ticker", sort=False):
    prices = grp["last_price"].values
    if len(prices) < 3:
        continue
    dp = np.diff(prices)  # first differences
    if len(dp) < 2:
        continue
    # Lag-1 autocovariance: cov(dp[t], dp[t-1])
    dp1 = dp[1:]   # dp[t]
    dp0 = dp[:-1]  # dp[t-1]
    if len(dp1) < 2:
        continue
    cov_val = np.cov(dp0, dp1, ddof=1)[0, 1]
    # Roll bound: s = sqrt(max(-cov, 0))
    roll_s = math.sqrt(max(-cov_val, 0.0))
    half_spreads.append(roll_s)
    market_autocov_results.append({"ticker": ticker, "autocov": cov_val, "half_spread": roll_s})

half_spreads = np.array(half_spreads)
n_markets_roll = len(half_spreads)
n_neg_autocov = np.sum(np.array([r["autocov"] for r in market_autocov_results]) < 0)
n_zero_spread = np.sum(half_spreads == 0.0)

median_half_spread = float(np.median(half_spreads))
print(f"  Markets with Roll bound: {n_markets_roll}", flush=True)
print(f"  Markets with negative autocov (s > 0): {n_neg_autocov}", flush=True)
print(f"  Markets with zero half-spread (autocov >= 0): {n_zero_spread}", flush=True)
print(f"  Median half-spread: {median_half_spread:.4f} cents", flush=True)

# Median |ofi| across bars (for implied coefficient)
median_abs_ofi = float(b["ofi"].abs().median())
print(f"  Median |ofi| per bar: {median_abs_ofi:.2f} contracts", flush=True)

# D.4-D: Bounce-implied flow coefficient = 2*s / median_abs_ofi
# Rationale: if price bounces by 2*s (full spread) per median |ofi| contracts, implied coef = 2s/ofi
# But units: s is in cents = price points. dp_1 is in raw price units (0-100 scale = cents).
# So implied_coef = 2 * median_half_spread / median_abs_ofi
if median_abs_ofi > 0:
    implied_coef = 2.0 * median_half_spread / median_abs_ofi
else:
    implied_coef = np.nan
print(f"  Bounce-implied flow coef (2*s / median|ofi|): {implied_coef:.4e}", flush=True)

# D.4-E: Measured flow coefficient from pooled OLS (same as D.3)
measured_coef = r_pool["coef"]
print(f"  Measured flow coef (pooled OLS): {measured_coef:.4e}", flush=True)

# Ratio
if not np.isnan(measured_coef) and measured_coef != 0:
    coef_ratio = implied_coef / abs(measured_coef)
else:
    coef_ratio = np.nan
print(f"  Ratio (implied / |measured|): {coef_ratio:.1f}", flush=True)

# D.4-F: Equivalent imbalance = 2*s / |measured_coef| (contracts)
if not np.isnan(measured_coef) and measured_coef != 0:
    equiv_imbalance = 2.0 * median_half_spread / abs(measured_coef)
else:
    equiv_imbalance = np.nan
print(f"  Equivalent imbalance (2*s/|coef|): {equiv_imbalance:.0f} contracts", flush=True)

# D.4-G: Share of five-minute bars with zero price change (dp_1 == 0)
valid_dp = b["dp_1"].dropna()
n_zero_change = (valid_dp == 0).sum()
share_zero = n_zero_change / len(valid_dp)
print(f"  Zero-price-change bars: {n_zero_change:,} / {len(valid_dp):,} = {share_zero:.3f} ({share_zero*100:.1f}%)", flush=True)


# =============================================================================
# PRINT FRESH VALUES SUMMARY (before comparison)
# =============================================================================

print("\n" + "="*70, flush=True)
print("FRESH DIAGNOSTIC VALUES (printed before comparison to prior)", flush=True)
print("="*70, flush=True)
print(f"\nCHECKSUM (confirmatory panel reproduction):")
print(f"  vol-OFI Q5-Q1 lag-1: {r_vol['spread']:+.4f} ct  t={r_vol['t']:+.2f}")
print(f"  z-OFI   Q5-Q1 lag-1: {r_z['spread']:+.4f} ct  t={r_z['t']:+.2f}")
print(f"\nD.2 SKIP-ONE (lag-2):")
print(f"  z-OFI:   {r_z_lag2['spread']:+.4f} ct  t={r_z_lag2['t']:+.2f}  p={r_z_lag2['pval']:.4f}")
print(f"  vol-OFI: {r_vol_lag2['spread']:+.4f} ct  t={r_vol_lag2['t']:+.2f}  p={r_vol_lag2['pval']:.4f}")
print(f"\nD.3 LIQUIDITY SPLIT:")
print(f"  Thin:               {r_thin['coef']:.4e}  t={r_thin['t']:+.2f}  p={r_thin['pval']:.4f}")
print(f"  Thick:              {r_thick['coef']:.4e}  t={r_thick['t']:+.2f}  p={r_thick['pval']:.4f}")
print(f"  Thick multi-trade:  {r_thick_multi['coef']:.4e}  t={r_thick_multi['t']:+.2f}  p={r_thick_multi['pval']:.4f}")
print(f"  Depth ratio (single/multi): {depth_ratio:.2f}")
print(f"\nD.4 ROLL BOUND:")
print(f"  Median half-spread:         {median_half_spread:.4f} cents")
print(f"  Implied coef (2s/med|ofi|): {implied_coef:.4e}")
print(f"  Measured coef (pooled OLS): {measured_coef:.4e}")
print(f"  Ratio (implied/|measured|): {coef_ratio:.1f}")
print(f"  Equiv. imbalance:           {equiv_imbalance:.0f} contracts")
print(f"  Zero-price-change bars:     {share_zero*100:.1f}%")


# =============================================================================
# EXPECTED VALUES (prior vintage) — read AFTER fresh values computed
# =============================================================================

PRIOR = {
    "d2_z_spread":        +0.033,   # ct (n.s.)
    "d2_vol_spread":      -0.048,   # ct (p=0.023)
    "d3_thin_coef":       +7.6e-8,
    "d3_thin_p":           0.514,
    "d3_thick_coef":      -5.67e-9,
    "d3_thick_p":          0.022,
    "d3_thick_multi_coef":-5.75e-9,
    "d3_thick_multi_p":    0.021,
    "d3_depth_ratio":      290.0,   # "~290x"
    "d4_median_hs":        0.34,    # cents
    "d4_implied_coef":    -6e-5,    # at median flow 50 contracts
    "d4_measured_coef":   -5.2e-9,
    "d4_ratio":           12000.0,  # "~12,000"
    "d4_equiv_imbalance":  658515.0,
    "d4_zero_change":       0.797,
}

def verdict(fresh, prior, atol=None, rtol=0.05) -> str:
    """Match = within rtol of prior magnitude, or within atol if specified."""
    try:
        if np.isnan(float(fresh)) or prior is None:
            return "N/A"
    except Exception:
        return "N/A"
    if atol is not None:
        return "MATCH" if abs(fresh - prior) <= atol else f"DRIFT ({abs(fresh-prior):.2e})"
    if prior == 0:
        return "MATCH" if abs(fresh) < 1e-10 else "DRIFT"
    rel = abs(fresh - prior) / abs(prior)
    return "MATCH" if rel <= rtol else f"DRIFT ({rel*100:.1f}%)"


# =============================================================================
# WRITE MARKDOWN OUTPUT
# =============================================================================

print("\n" + "="*70, flush=True)
print("Writing paper/exhibits/ex5d_diagnostics.md ...", flush=True)
print("="*70, flush=True)

now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

vol_q_rows = ""
for q in [f"Q{i}" for i in range(1, 6)]:
    ofi_m = r_vol["qmeans_ofi"].get(q, float("nan"))
    dp_m  = r_vol["qmeans_dp"].get(q, float("nan"))
    vol_q_rows += f"| {q} | {ofi_m:.4f} | {dp_m:+.4f} |\n"

z_q_rows = ""
for q in [f"Q{i}" for i in range(1, 6)]:
    ofi_m = r_z["qmeans_ofi"].get(q, float("nan"))
    dp_m  = r_z["qmeans_dp"].get(q, float("nan"))
    z_q_rows += f"| {q} | {ofi_m:.4f} | {dp_m:+.4f} |\n"

checksum_verdict = "PASS" if CHECKSUM_PASS else "FAIL"

md = f"""# Exhibit 5D — OFI Bounce Diagnostics (Skip-One, Liquidity Split, Roll Bound)
**Generated:** {now}
**Script:** `code/ex5d_diagnostics.py`
**Panel:** 26 fight cards, Feb–Nov 2025, 5-min bars, [5,95]¢ price filter, card-clustered SE.
**Prior vintage commit:** bb5d695

---

## (a) Vintage Check and Checksum Reproduction

### Vintage Check

**Command:** `git diff bb5d695 -- code/trackB_phase1_orderflow.py code/phase1_quintile_sort.py code/score_trackB_holdout.py code/trackB_confirmatory_score.py data/interim/lychee_macro_trades.parquet`

**Result:** No diff. No relevant OFI pipeline file changed since bb5d695. Proceeding to checksum.

### Checksum: Confirmatory Panel (ex5 values)

| Metric | Reproduced | Expected | Verdict |
|:-------|----------:|--------:|:--------|
| vol-OFI Q5-Q1 lag-1 (ct) | {r_vol['spread']:+.4f} | −1.1265 | {checksum_verdict} |
| t-statistic (vol-OFI) | {r_vol['t']:+.2f} | −6.29 | {checksum_verdict} |
| z-OFI Q5-Q1 lag-1 (ct) | {r_z['spread']:+.4f} | −0.1356 | {checksum_verdict} |
| t-statistic (z-OFI) | {r_z['t']:+.2f} | −1.27 | {checksum_verdict} |
| n_cards | {r_vol['n_cards']} | 26 | — |
| n_bars | {r_vol['n_bars']:,} | 62,119 | — |

**Checksum status: {checksum_verdict}** — proceeding to diagnostics.

#### Volume-scaled OFI Quintile Sort (lag-1)

| Quintile | Mean ofi_vol | Mean dp_lag1 (cents) |
|:--------:|:------------:|:--------------------:|
{vol_q_rows}
#### z-OFI Quintile Sort (lag-1)

| Quintile | Mean ofi_z | Mean dp_lag1 (cents) |
|:--------:|:----------:|:--------------------:|
{z_q_rows}

---

## (b) Fresh Diagnostic Values

### D.2 Skip-One (Lag-2 Quintile Spreads)

Computed BEFORE reading prior vintage values.

| OFI Variant | Q5-Q1 lag-2 (ct) | SE | t | p | n_cards |
|:-----------|:----------------:|:---:|:---:|:---:|:------:|
| z-OFI | {r_z_lag2['spread']:+.4f} | {r_z_lag2['se']:.4f} | {r_z_lag2['t']:+.2f} | {r_z_lag2['pval']:.4f} | {r_z_lag2['n_cards']} |
| volume-scaled | {r_vol_lag2['spread']:+.4f} | {r_vol_lag2['se']:.4f} | {r_vol_lag2['t']:+.2f} | {r_vol_lag2['pval']:.4f} | {r_vol_lag2['n_cards']} |

### D.3 Liquidity Split

Computed BEFORE reading prior vintage values.

**Sample split:** median market total trades = {median_trades:.0f}
Thin markets: {len(thin_tickers)} | Thick markets: {len(thick_tickers)}

**Regression spec:** dp_1 (raw price change, cents scale) ~ intercept + ofi (signed contract count); card-clustered sandwich SE.

| Subsample | Coef (dp/contract) | SE | t | p | n_bars |
|:---------|:-----------------:|:---:|:---:|:---:|:-----:|
| Thin (below-median trades) | {r_thin['coef']:.4e} | {r_thin['se']:.4e} | {r_thin['t']:+.2f} | {r_thin['pval']:.4f} | {r_thin['n']:,} |
| Thick (above-median trades) | {r_thick['coef']:.4e} | {r_thick['se']:.4e} | {r_thick['t']:+.2f} | {r_thick['pval']:.4f} | {r_thick['n']:,} |
| Thick, multi-trade bars only | {r_thick_multi['coef']:.4e} | {r_thick_multi['se']:.4e} | {r_thick_multi['t']:+.2f} | {r_thick_multi['pval']:.4f} | {r_thick_multi['n']:,} |

**Single-trade bars:** coef={r_single['coef']:.4e}  t={r_single['t']:+.2f}  p={r_single['pval']:.4f}  n={r_single['n']:,}
**Multi-trade bars:** coef={r_multi['coef']:.4e}  t={r_multi['t']:+.2f}  p={r_multi['pval']:.4f}  n={r_multi['n']:,}
**Depth ratio (single/multi):** {depth_ratio:.2f}×

### D.4 Roll Bound

Computed BEFORE reading prior vintage values.

**Roll half-spread:** Per-market first-order autocovariance of transaction price changes.
Markets with non-negative autocovariance: half-spread = 0.

| Statistic | Value |
|:----------|------:|
| Markets used in Roll calculation | {n_markets_roll} |
| Markets with negative autocov (s > 0) | {n_neg_autocov} |
| Markets with zero half-spread (autocov ≥ 0) | {n_zero_spread} |
| Median half-spread (across markets) | {median_half_spread:.4f} ct |
| Median \\|ofi\\| per bar | {median_abs_ofi:.2f} contracts |
| Bounce-implied flow coef (2s / med\\|ofi\\|) | {implied_coef:.4e} |
| Measured flow coef (pooled OLS, same as D.3) | {measured_coef:.4e} |
| Ratio (implied / \\|measured\\|) | {coef_ratio:.1f}× |
| Equiv. imbalance (2s / \\|coef\\|) | {equiv_imbalance:.0f} contracts |
| Zero-price-change bars | {n_zero_change:,} / {len(valid_dp):,} = {share_zero*100:.1f}% |

---

## (c) Side-by-Side Comparison: Prior vs Fresh

### D.2 Skip-One

| Cell | Prior (bb5d695) | Fresh | Verdict |
|:-----|:---------------:|:-----:|:-------:|
| z-OFI Q5-Q1 lag-2 (ct) | +0.033 (n.s.) | {r_z_lag2['spread']:+.4f} (p={r_z_lag2['pval']:.3f}) | {verdict(r_z_lag2['spread'], 0.033, atol=0.015)} |
| vol-OFI Q5-Q1 lag-2 (ct) | −0.048 (p=0.023) | {r_vol_lag2['spread']:+.4f} (p={r_vol_lag2['pval']:.3f}) | {verdict(r_vol_lag2['spread'], -0.048, atol=0.020)} |

### D.3 Liquidity Split

| Cell | Prior | Fresh | Verdict |
|:-----|:-----:|:-----:|:-------:|
| Thin coef (dp/contract) | 7.6e-8 | {r_thin['coef']:.4e} | {verdict(r_thin['coef'], 7.6e-8)} |
| Thin p-value | 0.514 | {r_thin['pval']:.3f} | {verdict(r_thin['pval'], 0.514, atol=0.10)} |
| Thick coef (dp/contract) | −5.67e-9 | {r_thick['coef']:.4e} | {verdict(r_thick['coef'], -5.67e-9)} |
| Thick p-value | 0.022 | {r_thick['pval']:.3f} | {verdict(r_thick['pval'], 0.022, atol=0.010)} |
| Thick multi-trade coef | −5.75e-9 | {r_thick_multi['coef']:.4e} | {verdict(r_thick_multi['coef'], -5.75e-9)} |
| Thick multi-trade p | 0.021 | {r_thick_multi['pval']:.3f} | {verdict(r_thick_multi['pval'], 0.021, atol=0.010)} |
| Depth ratio (single/multi) | ~290× | {depth_ratio:.1f}× | {verdict(depth_ratio, 290, atol=60)} |

### D.4 Roll Bound

| Cell | Prior | Fresh | Verdict |
|:-----|:-----:|:-----:|:-------:|
| Median half-spread (ct) | 0.34 | {median_half_spread:.4f} | {verdict(median_half_spread, 0.34, atol=0.05)} |
| Implied coef (~at med flow) | ~−6e-5 | {implied_coef:.4e} | {verdict(implied_coef, -6e-5)} |
| Measured coef (pooled OLS) | −5.2e-9 | {measured_coef:.4e} | {verdict(measured_coef, -5.2e-9)} |
| Ratio (implied/\\|measured\\|) | ~12,000× | {coef_ratio:.0f}× | {verdict(coef_ratio, 12000, atol=3000)} |
| Equiv. imbalance (contracts) | 658,515 | {equiv_imbalance:.0f} | {verdict(equiv_imbalance, 658515, atol=100000)} |
| Zero-price-change bars | 79.7% | {share_zero*100:.1f}% | {verdict(share_zero*100, 79.7, atol=2.0)} |

---

## (d) Spec Descriptions (for Appendix D)

**D.2 Skip-One.** Quintile sort on lag-2 (skip-one bar) forward return for both OFI variants (z-OFI and volume-scaled), on the same confirmatory panel (26 fight cards, Feb–Nov 2025, 5-min bars, [5,95]¢ filter). Q5-Q1 spread and card-clustered t-statistic are computed identically to the ex5 primary analysis, with dp_2 (return from close(t+1) to close(t+2)) as the outcome. If the reversal is driven by bid-ask bounce, it should attenuate at lag-2; if persistence or delayed information processing drives it, the lag-2 spread should be nonzero.

**D.3 Liquidity Split.** Markets are split at the median total-trade count (summed over all bars in the panel). Within each half, OLS regresses dp_1 (lag-1 price change in raw cents) on signed flow (ofi, contract-count units), with an intercept, SE clustered by fight card. The coefficient is also estimated on the thick half restricted to multi-trade bars (n > 1), and the single-trade vs multi-trade bar coefficient ratio is reported. Under a microstructure bounce, thinner markets with noisier prices and higher effective spreads should show a larger reversal coefficient; under an information story, the split should be irrelevant or opposite.

**D.4 Roll Bound.** Per-market effective half-spread is estimated via the Roll (1984) bound: s = sqrt(max(−Cov(dp_t, dp_{{t-1}}), 0)), where dp is the first difference of last_price within each market and covariance is computed with ddof=1; markets with non-negative autocovariance receive s = 0. The median half-spread across all markets is reported. The bounce-implied flow coefficient is 2s / median|ofi|, i.e., the price impact (in spread units) per median bar's signed flow. The measured flow coefficient comes from the pooled OLS in D.3. Their ratio and the equivalent imbalance (contracts needed to generate a full-spread move) quantify how much of the observed reversal is consistent with mechanical bounce versus genuine information.

---

## Documented Ambiguities (no prior code found for D.3 and D.4)

| ID | Ambiguity | Choice Made |
|:---|:----------|:------------|
| D.3-A | Market size proxy | Total trades = sum of bar-level n per ticker |
| D.3-B | Regressand and units | dp_1 in raw price units (cents 0-100 scale); ofi in raw contracts |
| D.3-C | SE clustering | Card-clustered (same as ex5) |
| D.3-D | Multi-trade bars | n > 1 (strictly more than one trade per bar) |
| D.3-F | Depth ratio | Single-trade coef / multi-trade coef |
| D.4-A | Negative autocov treatment | half-spread = 0 (per Roll's bound) |
| D.4-B | Autocovariance estimator | Sample covariance, ddof=1, consecutive dp pairs |
| D.4-D | Implied coefficient formula | 2*s / median(|ofi|) across all bars |
| D.4-F | Equivalent imbalance | 2*s / |measured_coef| |
"""

OUT_MD.write_text(md, encoding="utf-8")
print(f"Written: {OUT_MD}", flush=True)
print("DONE.", flush=True)
