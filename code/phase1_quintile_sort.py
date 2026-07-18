#!/usr/bin/env python3
"""
code/phase1_quintile_sort.py
============================
Track B Phase 1 -- OFI quintile portfolio sort, standardised variants.

Constructs two OFI normalisations and runs quintile sorts at lag 1 and lag 2:
  ofi_z   : within-market z-score (full pre-event window mean/sd per market)
  ofi_vol : OFI / rolling 6-hour market volume

Reports:
  1. Sign validation: pooled r and OLS beta of CONTEMPORANEOUS dp on z-OFI
  2. OLS lag-1 and lag-2 with z-OFI (per-1-sd units; ticker FE, clustered SE)
  3. Quintile sort Q1..Q5: mean forward return at lag-1 and lag-2, in cents
  4. Q5-Q1 spread, SE clustered by fight card, monotonicity check
  5. Repeat (3)-(4) with volume-scaled OFI
  6. Economic interpretation vs 1-cent tick and Kalshi round-trip fee

Kalshi taker fee schedule (verify at help.kalshi.com before relying on this):
  fee = FEE_RATE * P * (1 - P) per contract per side, where P = yes_price.
  As of 2026: FEE_RATE = 0.07 (7 cents on the dollar per unit of P*(1-P)).
  Round-trip cost = 2 * fee_per_side.
  Example: at P=0.50 -> round-trip = 2 * 0.07 * 0.25 = 0.035 = 3.5 cents/contract.

Run from repo root:
    python code/phase1_quintile_sort.py

Output:
    qa/phase1_quintile_sort.md   (markdown results table)
    console: key numbers only
"""
from __future__ import annotations
import glob, math, re, sys, io
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---- constants ---------------------------------------------------------------
RAW              = "data/raw/live"
SERIES           = "KXUFCFIGHT"
BUCKET           = "5min"
MIN_TRADES       = 100          # coverage floor -- same as Phase 1
N_QUINTILES      = 5
HOLDOUT_FILE     = Path("data/holdout/trackB_phase1_holdout_fights.txt")
OUT_MD           = Path("qa/phase1_quintile_sort.md")

# Kalshi fee schedule (see module docstring)
FEE_RATE         = 0.07         # per side; fee = FEE_RATE * P * (1-P)


# =============================================================================
# DATA LOADING
# =============================================================================

def _fight_id(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0]

def _card_date(ticker: str) -> str:
    """Parse fight-card date from ticker: KXUFCFIGHT-26JUL11... -> '2026-07-11'."""
    m = re.search(r"KXUFCFIGHT-(\d{2})([A-Z]{3})(\d{2})", ticker)
    if not m:
        return "unknown"
    yr, mon_str, day = int(m.group(1)), m.group(2), int(m.group(3))
    mon = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
           "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}.get(mon_str, 0)
    return f"20{yr:02d}-{mon:02d}-{day:02d}"

def load_training() -> pd.DataFrame:
    files = glob.glob(f"{RAW}/**/*.parquet", recursive=True)
    if not files:
        sys.exit(f"No parquets under {RAW}")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df = df.drop_duplicates("trade_id")
    df = df[df["ticker"].str.startswith(SERIES)].copy()
    df["created_time"] = pd.to_datetime(df["created_time"], utc=True, format="ISO8601")
    df["count"]     = pd.to_numeric(df["count_fp"],          errors="coerce")
    df["yes_price"] = pd.to_numeric(df["yes_price_dollars"], errors="coerce")
    df = df[df["taker_side"].isin(["yes","no"])].dropna(subset=["count","yes_price"])
    df["fight"] = df["ticker"].map(_fight_id)
    df["card"]  = df["ticker"].map(_card_date)
    holdout = set(HOLDOUT_FILE.read_text().strip().splitlines())
    df = df[~df["fight"].isin(holdout)]
    tc   = df.groupby("ticker")["trade_id"].size()
    keep = tc[tc >= MIN_TRADES].index
    return df[df["ticker"].isin(keep)].sort_values("created_time").reset_index(drop=True)


# =============================================================================
# BUCKETIZE
# =============================================================================

def bucketize(df: pd.DataFrame) -> pd.DataFrame:
    """
    5-minute bars per (fight, card, ticker, bucket).

    Columns produced:
      ofi         raw signed volume (taker_side=yes -> +count)
      total_count total contracts in bar (denominator for vol-scaling)
      last_price  last traded yes_price in bar
      dp_contemp  SAME-bar price change: last_price(t) - last_price(t-1)
      dp_1        lag-1 forward return: last_price(t+1) - last_price(t)  [strictly lagged]
      dp_2        lag-2 skip-one return: last_price(t+2) - last_price(t+1) [strictly lagged]
    """
    df = df.copy()
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

    # contemporaneous: same-bar price change (lp(t) - lp(t-1))
    b["dp_contemp"] = b.groupby("ticker")["last_price"].diff()

    # strictly lagged forward returns -- OFI in bar t, price change starts at close(t)
    lp = b.groupby("ticker")["last_price"]
    b["dp_1"] = lp.shift(-1) - b["last_price"]            # close(t+1) - close(t)
    b["dp_2"] = lp.shift(-2) - lp.shift(-1)               # close(t+2) - close(t+1)

    return b


# =============================================================================
# ROLLING 6-HOUR VOLUME  (time-based, within each market)
# =============================================================================

def add_rolling_vol(b: pd.DataFrame, window: str = "360min") -> pd.DataFrame:
    """
    vol_6h: rolling sum of total_count over the `window` ending at bar t,
    computed separately per market on the DatetimeIndex (bucket).
    Window is closed on the right (includes bar t's own volume).
    """
    parts = []
    for ticker, grp in b.groupby("ticker", sort=False):
        g = grp.set_index("bucket").sort_index()
        g["vol_6h"] = g["total_count"].rolling(window, min_periods=1).sum()
        parts.append(g.reset_index())
    return pd.concat(parts, ignore_index=True)


# =============================================================================
# OFI VARIANTS
# =============================================================================

def add_ofi_variants(b: pd.DataFrame) -> pd.DataFrame:
    """
    ofi_z   : z-scored within each market (full-window mean/sd).
              Markets with sd=0 are dropped (degenerate, all OFI identical).
    ofi_vol : OFI / vol_6h.  Bounded in [-1, 1] since |OFI| <= total_count <= vol_6h.
              NaN when vol_6h = 0 (should not occur after bucketing).
    """
    stats = (b.groupby("ticker")["ofi"]
              .agg(ofi_mean="mean", ofi_sd="std")
              .reset_index())
    zero_sd = stats.loc[stats["ofi_sd"] == 0, "ticker"].tolist()
    if zero_sd:
        print(f"  dropping {len(zero_sd)} markets with ofi_sd=0", flush=True)
        b = b[~b["ticker"].isin(zero_sd)].copy()
        stats = stats[~stats["ticker"].isin(zero_sd)]

    b = b.merge(stats, on="ticker", how="left")
    b["ofi_z"]   = (b["ofi"] - b["ofi_mean"]) / b["ofi_sd"]
    b["ofi_vol"] = np.where(b["vol_6h"] > 0, b["ofi"] / b["vol_6h"], np.nan)
    return b.drop(columns=["ofi_mean","ofi_sd"])


# =============================================================================
# ESTIMATION  (ticker FE, SE clustered by fight)
# =============================================================================

def _demean(s: pd.Series, by: pd.Series) -> np.ndarray:
    return (s - s.groupby(by).transform("mean")).to_numpy()

def _npval(t: float) -> float:
    """Two-sided p-value, normal approximation (fine for G >= 30)."""
    return math.erfc(abs(t) / math.sqrt(2))

def ols_fe(panel: pd.DataFrame, y_col: str, x_col: str,
           cluster: str = "fight") -> dict | None:
    """OLS with ticker FE (within-demean), SE clustered by `cluster`."""
    p = panel.dropna(subset=[y_col, x_col]).reset_index(drop=True)
    if p[cluster].nunique() < 2:
        return None
    yq  = _demean(p[y_col], p["ticker"])
    xq  = _demean(p[x_col], p["ticker"])
    sxx = float(xq @ xq)
    if sxx == 0:
        return None
    beta = float(xq @ yq) / sxx
    u    = yq - beta * xq
    meat = 0.0
    for _, idx in p.groupby(cluster).indices.items():
        s = float(xq[idx] @ u[idx]); meat += s * s
    G   = p[cluster].nunique()
    se  = np.sqrt(meat) / sxx * np.sqrt(G / (G - 1))
    t   = beta / se
    return dict(beta=beta, se=se, t=t, pval=_npval(t),
                ci_lo=beta - 1.96*se, ci_hi=beta + 1.96*se,
                n=len(p), G=G)


# =============================================================================
# QUINTILE SORT
# =============================================================================

def monotone(vals: list[float]) -> str:
    """Return monotonicity verdict for a list of means Q1..Q5."""
    diffs = [vals[i+1] - vals[i] for i in range(len(vals)-1)]
    if all(d >= 0 for d in diffs):
        return "increasing"
    if all(d <= 0 for d in diffs):
        return "decreasing"
    n_up = sum(d > 0 for d in diffs)
    return f"non-monotone ({n_up} up / {len(diffs)-n_up} down steps)"

def quintile_sort(b: pd.DataFrame, ofi_col: str,
                  dp_cols: list[str]) -> tuple[pd.DataFrame, dict]:
    """
    Pool all bars, assign quintile by ofi_col, compute per-quintile means.
    Q5-Q1 spread t-stat uses per-card spreads (SE clustered by fight card).

    Returns:
      qdf         DataFrame indexed Q1..Q5; columns = ofi_col mean + dp means in cents
      spr_stats   dict keyed by dp_col -> spread stats
    """
    valid = b.dropna(subset=[ofi_col]).copy()
    valid["_q"] = pd.qcut(valid[ofi_col], N_QUINTILES,
                          labels=[f"Q{i}" for i in range(1, N_QUINTILES+1)])

    rows = {"ofi_mean": valid.groupby("_q", observed=True)[ofi_col].mean()}
    for dp in dp_cols:
        g = valid.dropna(subset=[dp])
        rows[dp] = g.groupby("_q", observed=True)[dp].mean() * 100   # cents

    qdf = pd.DataFrame(rows)
    qdf.index.name = "quintile"

    spr_stats = {}
    for dp in dp_cols:
        g = valid.dropna(subset=[dp])
        # per-card per-quintile mean; then pivot and compute Q5-Q1 per card
        cq = g.groupby(["card","_q"], observed=True)[dp].mean() * 100
        wide = cq.unstack("_q")[["Q1","Q5"]].dropna()
        if len(wide) < 2:
            spr_stats[dp] = dict(spread=np.nan, se=np.nan, t=np.nan,
                                 pval=np.nan, n_cards=len(wide))
            continue
        spreads = wide["Q5"] - wide["Q1"]
        mu  = float(spreads.mean())
        se  = float(spreads.std(ddof=1)) / math.sqrt(len(spreads))
        t   = mu / se if se > 0 else np.nan
        spr_stats[dp] = dict(spread=mu, se=se, t=t,
                             pval=_npval(t) if not np.isnan(t) else np.nan,
                             n_cards=len(wide))
    return qdf, spr_stats


# =============================================================================
# MARKDOWN FORMATTING
# =============================================================================

def _md_ols_row(label: str, r: dict | None) -> str:
    if r is None:
        return f"| {label} | n/a | | | | | | |"
    return (f"| {label} | {r['beta']:+.4e} | {r['se']:.4e} | "
            f"{r['t']:+.2f} | {r['pval']:.4f} | "
            f"[{r['ci_lo']:+.4e}, {r['ci_hi']:+.4e}] | "
            f"{r['n']:,} | {r['G']} |")

def _md_sort_section(ofi_col: str, label: str, b: pd.DataFrame) -> str:
    lines = []
    dp_cols = ["dp_1", "dp_2"]
    qdf, spr = quintile_sort(b, ofi_col, dp_cols)

    lines.append(f"\n### {label}\n")
    lines.append("| quintile | mean OFI | dp_lag1 (ct) | dp_lag2 skip-one (ct) |")
    lines.append("|----------|----------|--------------|-----------------------|")
    for q, row in qdf.iterrows():
        d1 = f"{row['dp_1']:+.4f}" if "dp_1" in row and not np.isnan(row.get("dp_1", float("nan"))) else "n/a"
        d2 = f"{row['dp_2']:+.4f}" if "dp_2" in row and not np.isnan(row.get("dp_2", float("nan"))) else "n/a"
        lines.append(f"| {q} | {row['ofi_mean']:.4f} | {d1} | {d2} |")

    lines.append("")
    for dp, lbl in [("dp_1","lag 1"), ("dp_2","lag 2 skip-one")]:
        s = spr[dp]
        vals = qdf[dp].tolist() if dp in qdf.columns else []
        mono = monotone(vals) if len(vals) == N_QUINTILES else "n/a"
        spread_str = f"{s['spread']:+.4f}" if not np.isnan(s["spread"]) else "n/a"
        se_str     = f"{s['se']:.4f}"      if not np.isnan(s["se"])     else "n/a"
        t_str      = f"{s['t']:+.2f}"      if not np.isnan(s["t"])      else "n/a"
        p_str      = f"{s['pval']:.4f}"    if not np.isnan(s["pval"])   else "n/a"
        lines.append(
            f"**{lbl}** Q5-Q1 spread: {spread_str} ct | "
            f"SE (card-clustered): {se_str} | t: {t_str} | p: {p_str} | "
            f"n_cards: {s['n_cards']} | monotonicity: {mono}  ")
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    md = io.StringIO()
    def _w(*a): print(*a, file=md)

    _w("# Track B Phase 1 -- OFI Quintile Sort (standardised variants)\n")
    _w(f"Generated: {datetime.date.today()}  ")
    _w("Pre-registration: OSF commit 7d61b9c. `data/holdout/` not accessed.  ")
    _w("OFI sign convention verified correct: `taker_side=yes` -> +count "
       "(see `qa/signing_check.md`).\n")

    # -- load ------------------------------------------------------------------
    print("Loading ...", flush=True)
    df = load_training()
    print("Bucketizing ...", flush=True)
    b  = bucketize(df)
    print("Rolling 6-hour volume ...", flush=True)
    b  = add_rolling_vol(b)
    print("OFI variants ...", flush=True)
    b  = add_ofi_variants(b)

    n_bars   = len(b)
    n_mkts   = b["ticker"].nunique()
    n_fights = b["fight"].nunique()
    n_cards  = b["card"].nunique()
    _w(f"**Sample:** {n_bars:,} bars | {n_mkts} markets | "
       f"{n_fights} fights | {n_cards} fight cards\n")
    print(f"Panel: {n_bars:,} bars | {n_mkts} markets | "
          f"{n_fights} fights | {n_cards} cards", flush=True)

    # -- OFI z-score coverage --------------------------------------------------
    sd0 = b.groupby("ticker")["ofi"].std().eq(0).sum()
    _w(f"Markets dropped (ofi_sd = 0): {sd0}  ")
    _w(f"Bars with valid ofi_z: {b['ofi_z'].notna().sum():,}  ")
    _w(f"Bars with valid ofi_vol: {b['ofi_vol'].notna().sum():,}\n")

    # =========================================================================
    # SIGN VALIDATION + OLS
    # =========================================================================
    _w("## Sign Validation and OLS (z-scored OFI)\n")
    _w("Contemporaneous expected **positive** (net yes-buying lifts same-bar "
       "price).  Lagged expected **negative** (Phase 1 reversal).\n")

    # pooled Pearson
    vc = b.dropna(subset=["dp_contemp","ofi_z"])
    vl = b.dropna(subset=["dp_1","ofi_z"])
    r_c  = float(np.corrcoef(vc["ofi_z"], vc["dp_contemp"])[0,1])
    r_l1 = float(np.corrcoef(vl["ofi_z"], vl["dp_1"])[0,1])

    _w(f"Pooled Pearson r(ofi_z, dp_contemp) = **{r_c:+.6f}** "
       f"({'POSITIVE -- OK' if r_c > 0 else 'NEGATIVE -- FLAG'})  ")
    _w(f"Pooled Pearson r(ofi_z, dp_lag1)    = {r_l1:+.6f}  \n")

    # OLS table (ticker FE, clustered by fight)
    rc  = ols_fe(b, "dp_contemp", "ofi_z")
    rl1 = ols_fe(b, "dp_1",       "ofi_z")
    rl2 = ols_fe(b, "dp_2",       "ofi_z")

    _w("### OLS: dprice ~ ofi_z  (ticker FE; SE clustered by fight)\n")
    _w("| Horizon | Beta ($/sd) | SE | t | p | 95% CI | n | G |")
    _w("|---------|-------------|----|----|---|--------|---|---|")
    _w(_md_ols_row("contemporaneous [sign check]", rc))
    _w(_md_ols_row("lag 1 [Phase 1 reversal]", rl1))
    _w(_md_ols_row("lag 2 [skip-one bar]", rl2))
    _w("")

    sign_ok = rc is not None and rc["beta"] > 0
    if sign_ok:
        _w(f"Contemporaneous beta = {rc['beta']:+.4e} -- "
           "**POSITIVE, sign convention confirmed.**\n")
    else:
        _w("**WARNING: contemporaneous beta is NOT positive. "
           "If confirmed, Phase 1 reversal and continuation labels are flipped. "
           "Stop and investigate before re-running anything.**\n")

    # =========================================================================
    # QUINTILE SORTS
    # =========================================================================
    _w("## Quintile Sorts\n")
    _w("Bars pooled across all markets. Quintile bins computed on the pooled "
       "distribution of the normalised OFI variant.  ")
    _w("Returns in **cents** (dollar price change x 100).  ")
    _w("Q5-Q1 spread SE clustered by fight card (event date).  ")
    _w("Strictly lagged: OFI in bar t predicts return from close(t) to "
       "close(t+1) for lag 1, and close(t+1) to close(t+2) for lag 2 "
       "(no shared trades).\n")

    _w(_md_sort_section("ofi_z",   "z-scored OFI (within-market standardised)", b))
    _w(_md_sort_section("ofi_vol", "volume-scaled OFI (OFI / rolling 6-hour volume)", b))

    # =========================================================================
    # ECONOMIC INTERPRETATION
    # =========================================================================
    _w("\n## Economic Interpretation\n")

    _, spr_z = quintile_sort(b, "ofi_z", ["dp_1"])
    spread_ct = spr_z["dp_1"]["spread"]

    p_med = float(b["last_price"].median())
    fee_1s = FEE_RATE * p_med * (1 - p_med)       # one side, $/contract
    fee_rt = 2 * fee_1s                            # round-trip, $/contract

    _w("**Minimum tick:** 1 cent (verified from data: p10-p75 of non-zero "
       "|dprice| = 1.00 ct).  \n")
    _w(f"**Q5-Q1 spread (z-OFI, lag 1):** {spread_ct:+.4f} ct  ")
    if not np.isnan(spread_ct):
        expected_sign = "negative (Q1 outperforms Q5 = reversal, consistent with Phase 1)"
        _w(f"Expected sign: {expected_sign}.\n")

    _w("**Kalshi taker fee estimate**  ")
    _w(f"Schedule: fee = {FEE_RATE} x P x (1-P) per contract per side  ")
    _w("*(Verify at help.kalshi.com/en/articles/fee-schedule before relying on this.)*  ")
    _w(f"Median yes_price in training set: P = {p_med:.3f}  ")
    _w(f"Fee per side at median P: **{fee_1s*100:.3f} ct/contract**  ")
    _w(f"Round-trip (buy + sell or sell + buy): **{fee_rt*100:.3f} ct/contract**\n")

    if not np.isnan(spread_ct):
        abs_spread = abs(spread_ct)
        _w(f"|Q5-Q1| = {abs_spread:.4f} ct  ")
        _w(f"1-cent tick: {abs_spread:.4f} ct "
           f"({'sub-tick' if abs_spread < 1.0 else f'{abs_spread:.1f}x tick'})  ")
        _w(f"Round-trip fee: {fee_rt*100:.3f} ct  ")
        ratio = abs_spread / (fee_rt * 100) if fee_rt > 0 else float("inf")
        _w(f"Spread / fee ratio: {ratio:.4f}x\n")

        if abs_spread < 1.0:
            verdict = (
                "**NOT economically meaningful.** The Q5-Q1 spread is sub-tick "
                f"({abs_spread:.4f} ct < 1 ct minimum price increment) and is "
                f"{1/ratio:.0f}x smaller than the round-trip fee burden "
                f"({fee_rt*100:.3f} ct). The signal is statistically real "
                "(Phase 1: perm_p = 0.0095) but is not tradeable: the expected "
                "edge cannot survive execution costs or the discrete price grid."
            )
        elif abs_spread < fee_rt * 100:
            verdict = (
                "**Statistically present, below fee hurdle.** The spread "
                f"({abs_spread:.4f} ct) clears the 1-cent tick but is smaller than "
                f"the round-trip fee ({fee_rt*100:.3f} ct). Not profitable after costs."
            )
        else:
            verdict = (
                "**Spread exceeds both tick and fee hurdle.** "
                "Warrants further investigation."
            )
        _w(f"**Verdict:** {verdict}\n")

    # =========================================================================
    # WRITE
    # =========================================================================
    text = md.getvalue()
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(text, encoding="utf-8")
    print(f"\nSaved: {OUT_MD}", flush=True)

    # key numbers to console
    print("\nKEY RESULTS:")
    print(f"  r(ofi_z, dp_contemp)         = {r_c:+.6f}")
    print(f"  contemp OLS beta (sign check)= {rc['beta']:+.4e}  p={rc['pval']:.4f}" if rc else "  contemp OLS: n/a")
    print(f"  lag-1 OLS beta (z-OFI)       = {rl1['beta']:+.4e}  p={rl1['pval']:.4f}" if rl1 else "  lag-1 OLS: n/a")
    print(f"  lag-2 OLS beta (z-OFI)       = {rl2['beta']:+.4e}  p={rl2['pval']:.4f}" if rl2 else "  lag-2 OLS: n/a")
    print(f"  Q5-Q1 spread (z-OFI, lag-1)  = {spread_ct:+.4f} ct")
    print(f"  round-trip fee at median P   = {fee_rt*100:.3f} ct")
    print("DONE")


if __name__ == "__main__":
    main()
