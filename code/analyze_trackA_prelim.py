"""
code/analyze_trackA_prelim.py
Writes qa/trackA_prelim.md — nothing else printed.
"""
import os, sys, warnings
import pandas as pd
import numpy as np
import statsmodels.api as sm

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO    = "C:/Users/micha/OneDrive/Pulpit/Kalshi/Prediction_Markets_Public"
IN_PATH = f"{REPO}/data/clean/trackA_event_panel.parquet"
OUT_MD  = f"{REPO}/qa/trackA_prelim_v2.md"

# ── load & compute returns ────────────────────────────────────────────────────
df = pd.read_parquet(IN_PATH)
df = df[df["usable"]].copy()

# cents (prices are in dollars, multiply by 100)
df["impact"]    = (df["price_30m"]  - df["pre_price"])  * 100   # pre -> +30m
df["drift_4h"]  = (df["price_4h"]   - df["price_30m"]) * 100   # +30m -> +4h
df["drift_24h"] = (df["price_24h"]  - df["price_30m"]) * 100   # +30m -> +24h

# drop rows where any return is NaN
reg_df = df.dropna(subset=["impact", "drift_4h", "drift_24h"]).copy()

# cluster ID = integer encoding of event timestamp
reg_df["event_id"] = reg_df["release_time_utc"].rank(method="dense").astype(int)

SERIES_MAP = {
    "KXCPICOREYOY": "CPI",
    "KXPAYROLLS":   "Payrolls",
    "KXFED":        "FOMC",
}

# ── regression helper ─────────────────────────────────────────────────────────
def ols_cluster(sub, y_col, x_col, cluster_col):
    """OLS with cluster-robust SE. Returns (N, beta, tstat) or (N, nan, nan)."""
    sub = sub.dropna(subset=[y_col, x_col])
    n = len(sub)
    if n < 3 or sub[x_col].std() == 0:
        return n, np.nan, np.nan
    X = sm.add_constant(sub[x_col].values, has_constant="add")
    y = sub[y_col].values
    groups = sub[cluster_col].values
    n_clusters = len(np.unique(groups))
    # Use cluster-robust if enough clusters, else HC3
    if n_clusters >= 5:
        res = sm.OLS(y, X).fit(cov_type="cluster",
                               cov_kwds={"groups": groups},
                               use_t=True)
    else:
        res = sm.OLS(y, X).fit(cov_type="HC3", use_t=True)
    beta  = res.params[1]
    tstat = res.tvalues[1]
    return n, round(beta, 4), round(tstat, 2)

# ── run regressions ────────────────────────────────────────────────────────────
horizons  = [("drift_4h", "+30m→+4h"), ("drift_24h", "+30m→+24h")]
groupings = [("Pooled", reg_df)] + [
    (label, reg_df[reg_df["event_series"] == k])
    for k, label in SERIES_MAP.items()
]

results = []
for (grp_label, sub) in groupings:
    for (col, hz_label) in horizons:
        n_cl = sub["event_id"].nunique() if not sub.empty else 0
        n, beta, tstat = ols_cluster(sub, col, "impact", "event_id")
        cov_note = "cluster" if n_cl >= 5 else "HC3"
        results.append({
            "Group":    grp_label,
            "Horizon":  hz_label,
            "N":        n,
            "beta":     beta,
            "t":        tstat,
            "SE_type":  cov_note,
            "n_events": n_cl,
        })

res_df = pd.DataFrame(results)

# ── descriptive stats on returns ──────────────────────────────────────────────
desc = reg_df[["impact", "drift_4h", "drift_24h"]].describe().round(2)

# ── write markdown ─────────────────────────────────────────────────────────────
os.makedirs(f"{REPO}/qa", exist_ok=True)

lines = []
A = lines.append

A("# Track A — Macro Post-Announcement Drift: Preliminary Results")
A("")
A(f"**Date:** {pd.Timestamp.now().strftime('%Y-%m-%d')}  ")
A(f"**Status:** Pilot — N = 6 events. Kill rule N < 20 → result is **inconclusive by construction**. No inferential conclusion drawn.")
A("")
A("---")
A("")
A("## 1. Data")
A("")
A(f"- Source: `data/clean/trackA_event_panel.parquet`")
A(f"- Usable event × market rows: {len(reg_df)}")
A(f"- Events: {reg_df['release_time_utc'].nunique()} (3 event dates × 2 series each)")
A(f"- Series in panel: {', '.join(reg_df['event_series'].unique().tolist())}")
A("")
A("Contract selection: affected markets with expiry >72h after t0 (later-month contracts")
A("responding to the news; contracts settled by the print dropped).")
A("")
A("---")
A("")
A("## 2. Return Definitions (cents)")
A("")
A("| Return | Window | Formula |")
A("|--------|--------|---------|")
A("| Impact | pre → t0+30m | price_30m − pre_price |")
A("| Drift(4h) | t0+30m → t0+4h | price_4h − price_30m |")
A("| Drift(24h) | t0+30m → t0+24h | price_24h − price_30m |")
A("")
A("Pre-price = last trade in [t0−6h, t0). Prices in cents (×100 from dollars).")
A("")
A("**Descriptive statistics (cents):**")
A("")
A("```")
A(desc.to_string())
A("```")
A("")
A("---")
A("")
A("## 3. Regressions: Drift ~ Impact")
A("")
A("Model: `Drift = α + β·Impact + ε`  ")
A("SE: cluster-robust by event where n_events ≥ 5; HC3 otherwise (noted per cell).")
A("")
A("Interpretation: **β > 0** = underreaction (continuation); **β < 0** = overreaction (reversal); **β ≈ 0** = efficient.")
A("")

# Table header
A("| Group | Horizon | N | β | t | SE type | Events |")
A("|-------|---------|---|---|---|---------|--------|")
for _, r in res_df.iterrows():
    beta_s = f"{r['beta']:.4f}" if pd.notna(r['beta']) else "—"
    t_s    = f"{r['t']:.2f}"   if pd.notna(r['t'])    else "—"
    A(f"| {r['Group']} | {r['Horizon']} | {r['N']} | {beta_s} | {t_s} | {r['SE_type']} | {r['n_events']} |")

A("")
A("---")
A("")
A("## 4. Interpretation")
A("")

# Auto-generate interpretation per cell
for _, r in res_df.iterrows():
    if pd.isna(r["beta"]):
        interp = "insufficient variation"
    elif abs(r["beta"]) < 0.05 and abs(r["t"]) < 1.0:
        interp = "consistent with efficiency (β ≈ 0, |t| < 1)"
    elif r["beta"] > 0 and abs(r["t"]) >= 1.0:
        interp = f"directional underreaction (β = {r['beta']:.3f}, t = {r['t']:.2f}) — continuation signal, underpowered"
    elif r["beta"] < 0 and abs(r["t"]) >= 1.0:
        interp = f"directional overreaction (β = {r['beta']:.3f}, t = {r['t']:.2f}) — reversal signal, underpowered"
    else:
        interp = f"β = {r['beta']:.3f}, t = {r['t']:.2f} — inconclusive"
    A(f"- **{r['Group']} / {r['Horizon']}**: {interp}.")

A("")
A("**All results are inconclusive.** With 6 events any non-zero β is consistent with noise.")
A("Kill rule (N < 20) applies; revisit when N ≥ 20.")
A("")
A("---")
A("")
A("## 5. Attrition note")
A("")
attrition = (
    df.groupby("event_series")
    .agg(total_usable=("ticker", "count"),
         in_regression=("impact", lambda x: x.notna().sum()))
)
A("```")
A(attrition.to_string())
A("```")
A("")
A("Rows drop from usable → regression only where price_30m, price_4h, or price_24h is NaN")
A("(no trade in that window).")

md = "\n".join(lines)
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)
