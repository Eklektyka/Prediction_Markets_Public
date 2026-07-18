#!/usr/bin/env python3
"""
trackB_phase1_diagnostics.py -- three discriminating diagnostics for the Track B Phase 1 result.

The pre-registered regression (OSF commit 7d61b9c) found a significant NEGATIVE OFI
coefficient: mean reversion, not continuation. These diagnostics distinguish two
mechanisms that produce negative coefficients:

  Bid-ask bounce (mechanical)
    -- reversal concentrates entirely at lag 1 (the spread completes in one bar)
    -- predicted reversal at typical OFI ~= the effective half-spread
    -- worst in thin markets / wide-spread bars; vanishes in liquid markets

  Genuine behavioural overreaction
    -- reversal decays smoothly across lags 2, 3, 4, ... (price slowly corrects)
    -- predicted reversal >> effective spread at any plausible OFI
    -- survives in thick / liquid market splits

EXPLORATORY -- these are post-hoc mechanism tests, not pre-registered. No kill
rule is tied to this output. Results go to qa/trackB_phase1_diagnostics.txt.

Run from repo root:
    python trackB_phase1_diagnostics.py
"""
from __future__ import annotations
import glob, math, sys, io
from pathlib import Path
import numpy as np
import pandas as pd

# ---- constants (must match trackB_phase1_orderflow.py exactly) -----------
RAW                  = "data/raw/live"
SERIES               = "KXUFCFIGHT"
BUCKET               = "5min"
MIN_TRADES_PER_MKT   = 100
HOLDOUT_FILE         = Path("data/holdout/trackB_phase1_holdout_fights.txt")
MAX_LAG              = 5

# pre-registered result (qa/trackB_phase1_results.txt, commit 7d61b9c)
REG_BETA = -5.212126e-9
REG_SE   =  2.323193e-9


# ===========================================================================
# Data loading -- identical logic to trackB_phase1_orderflow.py
# ===========================================================================

def fight_id(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0]

def load_training() -> pd.DataFrame:
    files = glob.glob(f"{RAW}/**/*.parquet", recursive=True)
    if not files:
        sys.exit(f"No parquet files under {RAW}")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df = df[df["ticker"].str.startswith(SERIES)].copy()
    df = df.drop_duplicates("trade_id")
    df["created_time"] = pd.to_datetime(df["created_time"], utc=True, format="ISO8601")
    df["count"]     = pd.to_numeric(df["count_fp"],          errors="coerce")
    df["yes_price"] = pd.to_numeric(df["yes_price_dollars"], errors="coerce")
    df = df[df["taker_side"].isin(["yes", "no"])].dropna(subset=["count", "yes_price"])
    df["fight"] = df["ticker"].map(fight_id)

    # exclude sealed holdout
    holdout_fights = set(HOLDOUT_FILE.read_text().strip().splitlines())
    df = df[~df["fight"].isin(holdout_fights)]

    # coverage floor (same as pre-registered)
    tc   = df.groupby("ticker")["trade_id"].size()
    keep = tc[tc >= MIN_TRADES_PER_MKT].index
    return df[df["ticker"].isin(keep)].sort_values("created_time").reset_index(drop=True)


# ===========================================================================
# Extended bucketize -- produces lags 1..MAX_LAG
# ===========================================================================

def bucketize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signed"] = np.where(df["taker_side"] == "yes", df["count"], -df["count"])
    df["bucket"]  = df["created_time"].dt.floor(BUCKET)

    b = (df.groupby(["fight", "ticker", "bucket"])
           .agg(ofi        = ("signed",    "sum"),
                last_price = ("yes_price", "last"),
                n          = ("trade_id",  "size"),
                hi         = ("yes_price", "max"),
                lo         = ("yes_price", "min"))
           .reset_index()
           .sort_values(["ticker", "bucket"])
           .reset_index(drop=True))

    b["bar_range"] = b["hi"] - b["lo"]   # intrabar price range; loose spread proxy

    # lag-k last prices within each ticker (NaN when fewer than k bars remain)
    for k in range(1, MAX_LAG + 1):
        b[f"lp_{k}"] = b.groupby("ticker")["last_price"].shift(-k)

    # incremental dprice at lag k: price change *in* bar t+k, not cumulative
    b["dp_1"] = b["lp_1"] - b["last_price"]
    for k in range(2, MAX_LAG + 1):
        b[f"dp_{k}"] = b[f"lp_{k}"] - b[f"lp_{k-1}"]

    # cumulative dprice from bar t to t+k
    for k in range(1, MAX_LAG + 1):
        b[f"cum_{k}"] = b[f"lp_{k}"] - b["last_price"]

    return b


# ===========================================================================
# Estimation -- OLS with ticker FE (within-demeaning), SE clustered by fight
# ===========================================================================

def _demean(s: pd.Series, by: pd.Series) -> np.ndarray:
    return (s - s.groupby(by).transform("mean")).to_numpy()

def _norm_pval(t_stat: float) -> float:
    """Two-sided p-value; normal approximation, fine for G >= 30."""
    return math.erfc(abs(t_stat) / math.sqrt(2))

def ols(panel: pd.DataFrame, y_col: str) -> dict | None:
    """
    OLS with ticker FE (within-demean), SE clustered by fight.
    panel must have columns: y_col, ofi, ticker, fight.
    Returns None if fewer than 2 fights or degenerate design.
    """
    p = panel.dropna(subset=[y_col]).reset_index(drop=True)
    if p["fight"].nunique() < 2:
        return None

    yq  = _demean(p[y_col], p["ticker"])
    xq  = _demean(p["ofi"],  p["ticker"])
    sxx = float(xq @ xq)
    if sxx == 0:
        return None

    beta = float(xq @ yq) / sxx
    u    = yq - beta * xq

    # cluster-robust sandwich (groups are contiguous in reset index)
    meat = 0.0
    for _, idx in p.groupby("fight").indices.items():
        s = float(xq[idx] @ u[idx]); meat += s * s
    G   = p["fight"].nunique()
    se  = np.sqrt(meat) / sxx * np.sqrt(G / (G - 1))
    t   = beta / se
    return dict(beta=beta, se=se, t=t, pval=_norm_pval(t), n=len(p), G=G)


# ===========================================================================
# DIAGNOSTIC 1 -- Lag structure
# ===========================================================================

def diag_lag_structure(b: pd.DataFrame, out: io.StringIO) -> None:
    H  = "=" * 72
    H2 = "-" * 72
    _p = lambda *a, **kw: print(*a, **kw, file=out)

    _p(f"\n{H}")
    _p("DIAGNOSTIC 1 -- LAG STRUCTURE  (skip-one-bar test)")
    _p(H)
    _p("OFI(t) predicting the incremental price change at lag k.")
    _p("  Bounce       -> signal confined to lag 1; lags 2-5 ~= 0 and insignificant.")
    _p("  Overreaction -> signal decays gradually (still negative and significant at 2+).")
    _p("")

    hdr = f"  {'Lag':>4}  {'Beta':>12}  {'SE':>12}  {'t':>7}  {'p':>8}  {'n':>8}  {'G':>5}  note"
    _p("  Incremental dprice at lag k  [last_price(t+k) - last_price(t+k-1)]")
    _p(f"  {H2}")
    _p(hdr); _p(f"  {H2}")
    for k in range(1, MAX_LAG + 1):
        r = ols(b, f"dp_{k}")
        note = " <- pre-reg" if k == 1 else ""
        if r is None:
            _p(f"  {k:>4}  {'n/a':>12}"); continue
        _p(f"  {k:>4}  {r['beta']:>12.3e}  {r['se']:>12.3e}  {r['t']:>7.2f}"
           f"  {r['pval']:>8.4f}  {r['n']:>8,}  {r['G']:>5}{note}")

    _p("")
    _p("  Cumulative dprice at horizon k  [last_price(t+k) - last_price(t)]")
    _p(f"  {H2}")
    _p(hdr); _p(f"  {H2}")
    for k in range(1, MAX_LAG + 1):
        r = ols(b, f"cum_{k}")
        note = " <- pre-reg (= lag 1)" if k == 1 else ""
        if r is None:
            _p(f"  {k:>4}  {'n/a':>12}"); continue
        _p(f"  {k:>4}  {r['beta']:>12.3e}  {r['se']:>12.3e}  {r['t']:>7.2f}"
           f"  {r['pval']:>8.4f}  {r['n']:>8,}  {r['G']:>5}{note}")

    _p("")
    _p("  Read: if cum betas are flat (k=1 ~= k=2 ~= k=3), the reversal was complete")
    _p("  by lag 1 -> bounce. If cum betas grow more negative at k=2,3 -> overreaction.")


# ===========================================================================
# DIAGNOSTIC 2 -- Magnitude vs effective spread
# ===========================================================================

def _roll_spreads(b: pd.DataFrame) -> pd.Series:
    """
    Per-ticker Roll (1984) implied spread.
    In the lag panel: dp_1(t) = dp_t and dp_2(t) = dp_{t+1}, so
    Cov(dp_1, dp_2) within a market = Cov(dp_t, dp_{t+1}).
    Roll spread = 2 * sqrt(max(0, -Cov)).
    """
    results = {}
    valid = b.dropna(subset=["dp_1", "dp_2"])
    for ticker, grp in valid.groupby("ticker"):
        if len(grp) < 6:
            continue
        c = np.cov(grp["dp_1"].values, grp["dp_2"].values)[0, 1]
        results[ticker] = 2.0 * math.sqrt(max(0.0, -c))
    return pd.Series(results)

def diag_magnitude_spread(b: pd.DataFrame, out: io.StringIO) -> None:
    H  = "=" * 72
    _p = lambda *a, **kw: print(*a, **kw, file=out)

    b1 = b.dropna(subset=["dp_1"]).copy()

    _p(f"\n{H}")
    _p("DIAGNOSTIC 2 -- MAGNITUDE vs EFFECTIVE SPREAD")
    _p(H)
    _p("Is |beta x typical_OFI| ~= the effective half-spread?")
    _p("  Bounce    -> predicted reversal at median OFI ~= Roll half-spread.")
    _p("  Real sig. -> predicted reversal << Roll spread (or >> at plausible OFI).")
    _p(f"  (pre-registered beta = {REG_BETA:.4e}, SE = {REG_SE:.4e})")
    _p("")

    # --- OFI distribution ---
    ofi_abs = b1["ofi"].abs()
    pcts    = [10, 25, 50, 75, 90, 99]
    _p("  |OFI| distribution (net contracts per 5-min bar):")
    vals = {p: np.percentile(ofi_abs, p) for p in pcts}
    row  = "  " + "  ".join(f"p{p}={vals[p]:>9,.0f}" for p in pcts)
    _p(row)
    _p(f"  mean={ofi_abs.mean():>10,.1f}  sd={ofi_abs.std():>10,.1f}  "
       f"bars with OFI=0: {(ofi_abs==0).mean():.1%}")
    _p("")

    # --- predicted reversal at each OFI percentile ---
    _p("  Predicted reversal |beta x OFI| at each |OFI| percentile (dollars / cents):")
    for p in pcts:
        pred_d = abs(REG_BETA * vals[p])
        pred_c = pred_d * 100
        _p(f"    p{p:2d}  OFI={vals[p]:>10,.0f}  ->  {pred_d:.6f} $ = {pred_c:.4f} ct")
    _p("")

    # --- actual dprice distribution ---
    dp_nz = b1.loc[b1["dp_1"] != 0, "dp_1"].abs()
    _p("  Actual |dprice| at lag 1 (non-zero moves only):")
    dp_pct = {p: np.percentile(dp_nz, p) for p in [10, 25, 50, 75, 90]}
    _p("  " + "  ".join(f"p{p}={dp_pct[p]*100:.3f}ct" for p in [10, 25, 50, 75, 90]))
    _p(f"  fraction of bars with zero price move: {(b1['dp_1']==0).mean():.1%}")
    tick_vals = sorted(dp_nz[dp_nz > 0].unique())[:6]
    _p(f"  smallest observed non-zero moves: {[f'{v*100:.2f}ct' for v in tick_vals]}")
    _p("")

    # --- Roll spread ---
    roll = _roll_spreads(b)
    _p("  Roll (1984) implied spread (per market, using Cov(dp_t, dp_{t+1})):")
    if roll.empty:
        _p("  (insufficient data to estimate)")
    else:
        _p(f"  markets estimated: {len(roll)} / {b['ticker'].nunique()}")
        _p(f"  p25={roll.quantile(.25)*100:.3f}ct  median={roll.median()*100:.3f}ct  "
           f"p75={roll.quantile(.75)*100:.3f}ct  mean={roll.mean()*100:.3f}ct")
        _p(f"  markets with zero Roll spread (Cov >= 0): "
           f"{(roll==0).sum()} ({(roll==0).mean():.1%})")
        _p("")

        med_roll = roll.median()
        med_ofi  = vals[50]
        pred_med = abs(REG_BETA * med_ofi)
        _p("  KEY COMPARISON:")
        _p(f"    Predicted reversal at median |OFI| ({med_ofi:,.0f} contracts):")
        _p(f"      |beta x median_OFI| = {pred_med*100:.4f} ct")
        _p(f"    Roll implied spread (median market):  {med_roll*100:.3f} ct")
        _p(f"    Roll half-spread:                     {med_roll/2*100:.3f} ct")
        if med_roll > 0:
            ratio = pred_med / (med_roll / 2)
            _p(f"    Ratio (predicted / half-spread):      {ratio:.4f}x")
            _p(f"    OFI needed to match half-spread:      "
               f"{(med_roll/2)/abs(REG_BETA):>12,.0f} contracts")


# ===========================================================================
# DIAGNOSTIC 3 -- Concentration in thin markets / wide-spread bars
# ===========================================================================

def _fit_row(label: str, subset: pd.DataFrame, y_col: str, _p) -> None:
    r = ols(subset, y_col)
    if r is None:
        _p(f"    {label:<36}  insufficient data")
    else:
        _p(f"    {label:<36}  beta={r['beta']:>10.3e}  t={r['t']:>6.2f}"
           f"  p={r['pval']:.4f}  n={r['n']:>7,}  G={r['G']}")

def diag_concentration(b: pd.DataFrame, out: io.StringIO) -> None:
    H  = "=" * 72
    _p = lambda *a, **kw: print(*a, **kw, file=out)

    b1 = b.dropna(subset=["dp_1"]).reset_index(drop=True)

    _p(f"\n{H}")
    _p("DIAGNOSTIC 3 -- CONCENTRATION (thin markets / wide-spread bars)")
    _p(H)
    _p("Bounce is worst exactly where books are thin and spreads are wide.")
    _p("  Bounce    -> signal disappears in thick / narrow-spread splits.")
    _p("  Real sig. -> effect survives across liquidity regimes.")
    _p("")

    # (a) Bar depth: n = trades per bar
    n25, n75 = b1["n"].quantile(0.25), b1["n"].quantile(0.75)
    _p(f"  (a) Bar depth split  (n = trades per 5-min bar; p25={n25:.0f}  p75={n75:.0f})")
    _fit_row(f"Thin bars  (n <= {n25:.0f})",  b1[b1["n"] <= n25], "dp_1", _p)
    _fit_row(f"Thick bars (n >= {n75:.0f})",  b1[b1["n"] >= n75], "dp_1", _p)
    _fit_row("All bars                        ", b1,                "dp_1", _p)

    # (b) Market liquidity: total trades per ticker
    mkt_n      = b.groupby("ticker")["n"].sum()
    med_n      = mkt_n.median()
    thin_mkts  = mkt_n[mkt_n <  med_n].index
    thick_mkts = mkt_n[mkt_n >= med_n].index
    _p("")
    _p(f"  (b) Market liquidity split  (total trades per market; median={med_n:,.0f})")
    _fit_row("Thin markets  (< median)",   b1[b1["ticker"].isin(thin_mkts)],  "dp_1", _p)
    _fit_row("Thick markets (>= median)",  b1[b1["ticker"].isin(thick_mkts)], "dp_1", _p)
    _fit_row("All markets                 ", b1,                               "dp_1", _p)

    # (c) Intrabar price range (proxy for book thinness within each bar)
    rng75 = b1["bar_range"].quantile(0.75)
    _p("")
    _p(f"  (c) Intrabar range split  (hi - lo within bar; p75={rng75*100:.2f}ct)")
    _p(f"      Wide range -> thin book / bounce-prone; Narrow range -> tighter book.")
    _fit_row(f"Wide range   (>= {rng75*100:.2f}ct)",  b1[b1["bar_range"] >= rng75], "dp_1", _p)
    _fit_row(f"Narrow range (<  {rng75*100:.2f}ct)",  b1[b1["bar_range"] <  rng75], "dp_1", _p)
    _fit_row("All bars                        ",       b1,                            "dp_1", _p)

    # (d) Interaction: thick bars AND thick markets (most demanding filter)
    both_thick = b1[b1["ticker"].isin(thick_mkts) & (b1["n"] >= n75)]
    _p("")
    _p("  (d) Most demanding filter: thick markets AND thick bars (both >= p75)")
    _fit_row("Thick mkt + thick bar",  both_thick, "dp_1", _p)
    _fit_row("All                  ",  b1,         "dp_1", _p)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    out = io.StringIO()   # collect all output; tee to stdout + file at end

    def _p(*a, **kw): print(*a, **kw, file=out)

    _p("=" * 72)
    _p("TRACK B PHASE 1 -- MECHANISM DIAGNOSTICS  (exploratory, not pre-registered)")
    _p("=" * 72)
    _p(f"Pre-registered result: beta={REG_BETA:.4e}, SE={REG_SE:.4e}, perm_p=0.0095")
    _p("Signal is statistically significant but NEGATIVE (mean reversion, not continuation).")
    _p("These diagnostics test whether the reversal is mechanical (bounce) or behavioural.\n")

    print("Loading training data ...", flush=True)
    df = load_training()
    _p(f"Data: {len(df):,} trades  |  {df['ticker'].nunique()} markets  "
       f"|  {df['fight'].nunique()} fights  (holdout excluded, coverage floor applied)")

    print("Bucketizing (lags 1-5) ...", flush=True)
    b  = bucketize(df)
    n1 = b["dp_1"].notna().sum()
    _p(f"Panel: {len(b):,} bar-observations  |  {n1:,} with lag-1 dprice available\n")

    diag_lag_structure(b, out)
    diag_magnitude_spread(b, out)
    diag_concentration(b, out)

    _p(f"\n{'='*72}")
    _p("SUMMARY SCORECARD")
    _p(f"{'='*72}")
    _p("Fill in after reading the numbers above:")
    _p("  Lag 2 incremental beta significant?     ___  (bounce -> no,  overreaction -> yes)")
    _p("  Cum beta grows more negative at k>1?    ___  (bounce -> flat, overreaction -> yes)")
    _p("  Pred. reversal at median OFI vs spread: ___  (bounce -> ~= half-spread)")
    _p("  Signal survives thick-bar split?        ___  (bounce -> weaker/gone)")
    _p("  Signal survives thick-market split?     ___  (bounce -> weaker/gone)")
    _p("  Signal survives wide-range exclusion?   ___  (bounce -> gone without wide bars)")

    text = out.getvalue()
    # write file as UTF-8 (safe); print to stdout with replacement for any stray chars
    qa = Path("qa/trackB_phase1_diagnostics.txt")
    qa.parent.mkdir(exist_ok=True)
    qa.write_text(text, encoding="utf-8")

    sys.stdout.buffer.write(text.encode(sys.stdout.encoding or "utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    print(f"\nSaved -> {qa}")

if __name__ == "__main__":
    main()
