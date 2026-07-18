#!/usr/bin/env python3
"""
trackB_phase1_quintile_sort.py -- OFI quintile sort + contemporaneous sign validation.

Non-circular sign check: OLS of same-bar (contemporaneous) price change on z-scored
OFI. Expected beta POSITIVE -- net yes-buying pushes price up within the bar.
This is the complement to the Phase 1 lagged regression (beta negative = reversal).

Also reports:
  - Pooled Pearson r(dp_contemp, ofi_z)
  - OLS contemporaneous: dp_contemp ~ ofi_z  (ticker FE, SE clustered by fight)
  - OLS lagged (lag 1): dp_1       ~ ofi_z  (same spec, for comparison)
  - Quintile-sort table: mean dp_contemp and mean dp_1 per OFI quintile

OFI is z-scored within each market (mean 0, sd 1) before binning and regression,
so quintiles and coefficients are comparable across markets of different size.

Run from repo root:
    python trackB_phase1_quintile_sort.py
"""
from __future__ import annotations
import glob, math, sys, io
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW                = "data/raw/live"
SERIES             = "KXUFCFIGHT"
BUCKET             = "5min"
MIN_TRADES_PER_MKT = 100
HOLDOUT_FILE       = Path("data/holdout/trackB_phase1_holdout_fights.txt")
QA_DIR             = Path("qa")
N_QUINTILES        = 5


# ===========================================================================
# Data loading -- identical pipeline to trackB_phase1_orderflow.py
# ===========================================================================

def fight_id(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0]

def load_training() -> pd.DataFrame:
    files = glob.glob(f"{RAW}/**/*.parquet", recursive=True)
    if not files:
        sys.exit(f"No parquet files under {RAW}")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df = df.drop_duplicates("trade_id")
    df = df[df["ticker"].str.startswith(SERIES)].copy()
    df["created_time"] = pd.to_datetime(df["created_time"], utc=True, format="ISO8601")
    df["count"]     = pd.to_numeric(df["count_fp"],          errors="coerce")
    df["yes_price"] = pd.to_numeric(df["yes_price_dollars"], errors="coerce")
    df = df[df["taker_side"].isin(["yes", "no"])].dropna(subset=["count", "yes_price"])
    df["fight"] = df["ticker"].map(fight_id)

    holdout = set(HOLDOUT_FILE.read_text().strip().splitlines())
    df = df[~df["fight"].isin(holdout)]

    tc   = df.groupby("ticker")["trade_id"].size()
    keep = tc[tc >= MIN_TRADES_PER_MKT].index
    return df[df["ticker"].isin(keep)].sort_values("created_time").reset_index(drop=True)


# ===========================================================================
# Bucketize -- adds contemporaneous dprice and z-scored OFI
# ===========================================================================

def bucketize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signed"] = np.where(df["taker_side"] == "yes", df["count"], -df["count"])
    df["bucket"]  = df["created_time"].dt.floor(BUCKET)

    b = (df.groupby(["fight", "ticker", "bucket"])
           .agg(ofi        = ("signed",    "sum"),
                last_price = ("yes_price", "last"),
                n          = ("trade_id",  "size"))
           .reset_index()
           .sort_values(["ticker", "bucket"])
           .reset_index(drop=True))

    # contemporaneous dprice: price change WITHIN bar t vs previous bar
    # = last_price(t) - last_price(t-1); NaN for first bar of each market
    b["dp_contemp"] = b.groupby("ticker")["last_price"].diff()

    # lagged dprice: price change in next bar (Phase 1 response)
    b["dp_1"] = b.groupby("ticker")["last_price"].shift(-1) - b["last_price"]

    # z-score OFI within each market
    mkt_stats = b.groupby("ticker")["ofi"].agg(mean="mean", std="std")
    b = b.join(mkt_stats, on="ticker")
    b["ofi_z"] = (b["ofi"] - b["mean"]) / b["std"].replace(0.0, np.nan)
    b = b.drop(columns=["mean", "std"])

    return b


# ===========================================================================
# Estimation -- OLS with ticker FE, SE clustered by fight
# ===========================================================================

def _demean(s: pd.Series, by: pd.Series) -> np.ndarray:
    return (s - s.groupby(by).transform("mean")).to_numpy()

def _norm_pval(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2))

def ols(panel: pd.DataFrame, y_col: str, x_col: str = "ofi_z") -> dict | None:
    p = panel.dropna(subset=[y_col, x_col]).reset_index(drop=True)
    if p["fight"].nunique() < 2:
        return None
    yq  = _demean(p[y_col], p["ticker"])
    xq  = _demean(p[x_col], p["ticker"])
    sxx = float(xq @ xq)
    if sxx == 0:
        return None
    beta = float(xq @ yq) / sxx
    u    = yq - beta * xq
    meat = 0.0
    for _, idx in p.groupby("fight").indices.items():
        s = float(xq[idx] @ u[idx]); meat += s * s
    G   = p["fight"].nunique()
    se  = np.sqrt(meat) / sxx * np.sqrt(G / (G - 1))
    t   = beta / se
    ci_lo, ci_hi = beta - 1.96 * se, beta + 1.96 * se
    return dict(beta=beta, se=se, t=t, pval=_norm_pval(t),
                ci_lo=ci_lo, ci_hi=ci_hi, n=len(p), G=G)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    out = io.StringIO()
    def _p(*a, **kw): print(*a, **kw, file=out)

    _p("=" * 72)
    _p("TRACK B PHASE 1 -- OFI QUINTILE SORT + CONTEMPORANEOUS SIGN CHECK")
    _p("=" * 72)
    _p("OFI z-scored within each market.  Ticker FE, SE clustered by fight.")
    _p("Contemporaneous expected POSITIVE; lagged (Phase 1) expected NEGATIVE.\n")

    print("Loading ...", flush=True)
    df = load_training()
    print("Bucketizing ...", flush=True)
    b  = bucketize(df)

    n_contemp = b.dropna(subset=["dp_contemp", "ofi_z"]).shape[0]
    n_lag1    = b.dropna(subset=["dp_1",       "ofi_z"]).shape[0]
    _p(f"Panel: {len(b):,} bars  |  {b['ticker'].nunique()} markets  "
       f"|  {b['fight'].nunique()} fights")
    _p(f"       {n_contemp:,} bars with contemporaneous dprice  |  "
       f"{n_lag1:,} bars with lag-1 dprice\n")

    # -----------------------------------------------------------------------
    # Pooled Pearson correlations
    # -----------------------------------------------------------------------
    valid_c = b.dropna(subset=["dp_contemp", "ofi_z"])
    valid_l = b.dropna(subset=["dp_1",       "ofi_z"])
    r_contemp = float(np.corrcoef(valid_c["ofi_z"], valid_c["dp_contemp"])[0, 1])
    r_lag1    = float(np.corrcoef(valid_l["ofi_z"], valid_l["dp_1"]      )[0, 1])

    _p("-" * 72)
    _p("POOLED PEARSON CORRELATIONS  (no FE, raw z-OFI vs dprice)")
    _p("-" * 72)
    _p(f"  r(ofi_z, dp_contemp) = {r_contemp:+.6f}   [expected > 0]")
    _p(f"  r(ofi_z, dp_lag1)    = {r_lag1:+.6f}   [expected < 0, Phase 1 result]")

    # -----------------------------------------------------------------------
    # OLS: contemporaneous and lag-1, side by side
    # -----------------------------------------------------------------------
    rc = ols(b, "dp_contemp")
    rl = ols(b, "dp_1")

    _p(f"\n{'-'*72}")
    _p("OLS REGRESSIONS  (ticker FE, SE clustered by fight)")
    _p(f"{'-'*72}")
    _p(f"  {'Horizon':<20}  {'Beta':>12}  {'SE':>12}  {'t':>7}  {'p':>8}  "
       f"{'95% CI':^22}  {'n':>8}  {'G':>5}")
    _p(f"  {'-'*110}")

    def _row(label, r, note=""):
        if r is None:
            _p(f"  {label:<20}  insufficient data")
            return
        ci = f"[{r['ci_lo']:+.3e}, {r['ci_hi']:+.3e}]"
        _p(f"  {label:<20}  {r['beta']:>12.4e}  {r['se']:>12.4e}  {r['t']:>7.2f}"
           f"  {r['pval']:>8.4f}  {ci:^22}  {r['n']:>8,}  {r['G']:>5}  {note}")

    _row("contemporaneous", rc, "<-- sign check (expect +)")
    _row("lag 1 (Phase 1)", rl, "<-- pre-reg result (expect -)")

    if rc is not None and rl is not None:
        sign_ok = rc["beta"] > 0
        _p(f"\n  Sign check: beta_contemp = {rc['beta']:+.4e}  "
           f"-> {'POSITIVE -- convention confirmed' if sign_ok else 'NEGATIVE -- FLAG: sign may be wrong'}")
        if not sign_ok:
            _p("\n  *** WARNING: contemporaneous beta is negative. ***")
            _p("  *** If confirmed, Phase 1 reversal <-> continuation flip.  ***")
            _p("  *** Stop and investigate before re-running anything.        ***")

    # -----------------------------------------------------------------------
    # Quintile sort table
    # -----------------------------------------------------------------------
    _p(f"\n{'-'*72}")
    _p("QUINTILE SORT  (z-scored OFI; bars sorted into 5 bins)")
    _p(f"{'-'*72}")

    valid = b.dropna(subset=["ofi_z"]).copy()
    valid["quintile"] = pd.qcut(valid["ofi_z"], N_QUINTILES,
                                labels=[f"Q{i}" for i in range(1, N_QUINTILES + 1)])

    # Mean OFI_z, contemporaneous dprice, lag-1 dprice, and bar count per quintile
    qstats = (valid.groupby("quintile", observed=True)
              .agg(
                  ofi_z_mean   = ("ofi_z",      "mean"),
                  dp_c_mean    = ("dp_contemp",  "mean"),
                  dp_1_mean    = ("dp_1",        "mean"),
                  n_bars       = ("ofi_z",       "size"),
              ))

    hdr = (f"  {'Quintile':>8}  {'Mean z-OFI':>12}  "
           f"{'dp_contemp':>12}  {'dp_lag1':>12}  {'n_bars':>8}")
    _p(hdr)
    _p(f"  {'-'*58}")
    for q, row in qstats.iterrows():
        dc = f"{row['dp_c_mean']:>+.5f}" if not np.isnan(row["dp_c_mean"]) else "    n/a"
        d1 = f"{row['dp_1_mean']:>+.5f}" if not np.isnan(row["dp_1_mean"]) else "    n/a"
        _p(f"  {str(q):>8}  {row['ofi_z_mean']:>12.4f}  {dc:>12}  {d1:>12}  {int(row['n_bars']):>8,}")

    _p(f"\n  dp_contemp: price change in SAME bar [last_price(t) - last_price(t-1)]")
    _p(f"  dp_lag1:    price change in NEXT bar [last_price(t+1) - last_price(t)]")
    _p(f"  Expected: dp_contemp monotone increasing Q1->Q5 (sign check).")
    _p(f"            dp_lag1   monotone decreasing Q1->Q5 (Phase 1 reversal).")

    # -----------------------------------------------------------------------
    # Plot
    # -----------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    fig.suptitle("OFI Quintile Sort (z-scored within market)\n"
                 "Ticker FE removed; error bars = +/-1 SE across bars",
                 fontsize=10)

    def _quintile_se(col, valid):
        return valid.groupby("quintile", observed=True)[col].sem()

    for ax, col, label, color, expected in [
        (ax1, "dp_contemp", "Contemporaneous dprice (same bar)", "steelblue",
         "Expected: monotone increasing (sign check)"),
        (ax2, "dp_1",       "Lag-1 dprice (next bar)",           "firebrick",
         "Expected: monotone decreasing (Phase 1 reversal)"),
    ]:
        means = qstats[f"{col.replace('dp_','dp_')}_mean".replace(
                "dp_contemp_mean","dp_c_mean").replace("dp_1_mean","dp_1_mean")]
        # rebuild per-column
        grp_col = valid.groupby("quintile", observed=True)[col]
        means   = grp_col.mean()
        ses     = grp_col.sem()
        qs      = [f"Q{i}" for i in range(1, N_QUINTILES + 1)]
        ax.bar(qs, means.values, yerr=ses.values, color=color, alpha=0.75,
               capsize=4, error_kw={"linewidth": 1})
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_xlabel("OFI quintile (Q1=most negative, Q5=most positive)", fontsize=8)
        ax.set_ylabel("Mean price change ($)", fontsize=8)
        ax.set_title(f"{label}\n{expected}", fontsize=8)
        ax.tick_params(labelsize=8)

    plt.tight_layout()
    plot_path = QA_DIR / "trackB_phase1_quintile_sort.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    _p(f"\nPlot saved: {plot_path}")

    # -----------------------------------------------------------------------
    # Write output
    # -----------------------------------------------------------------------
    text = out.getvalue()
    sys.stdout.buffer.write(text.encode(sys.stdout.encoding or "utf-8", errors="replace"))
    sys.stdout.buffer.flush()

    txt_path = QA_DIR / "trackB_phase1_quintile_sort.txt"
    txt_path.write_text(text, encoding="utf-8")
    print(f"\nSaved: {txt_path}")


if __name__ == "__main__":
    main()
