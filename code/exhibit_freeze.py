#!/usr/bin/env python3
"""
code/exhibit_freeze.py
======================
Exhibit freeze — reproduces all Phase 2 paper exhibits from frozen panel.

Source:   data/clean/phase2_full_panel.parquet  (2025 era, 182 fights)
Outputs:  paper/exhibits/
            ex1_sample.{csv,md}
            ex2_ccf.{csv,md}
            ex3_jump.{csv,md}
            ex4_gap.{csv,md}
            ex5_ownflow.{csv,md}
            MANIFEST.md

Bootstrap: B=1000, seed=42, two-stage:
    Stage 1 — precompute per-fight statistics.
    Stage 2 — resample fight rows with replacement; recompute aggregate.
    CI = [2.5th, 97.5th] percentile of bootstrap distribution.
"""
from __future__ import annotations
import sys, time, io, math
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT    = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
PANEL   = ROOT / "data/clean/phase2_full_panel.parquet"
XWALK   = ROOT / "data/meta/ufc_crosswalk.parquet"
OUT_DIR = ROOT / "paper/exhibits"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── constants ─────────────────────────────────────────────────────────────────
# MUDBOR MAD=22.49c, SAIRUF MAD=20.30c — PM side inverted, excluded.
# HARFER — 0 co-active bars, no data, excluded.
# SPIGAZ MAD=4.80c — crosswalk remap validated (hygiene_block1 PASS), reincluded.
PM_FLIP_EXCLUDE = {
    "20250823_MUDBOR", "20250906_HARFER",
    "20250906_SAIRUF",
}
JUMP_THRESH  = 0.03       # 3 cents (prices in 0-1 scale)
JUMP_BIG     = 0.05       # 5 cents
BOTH_PCT_MIN = 25.0       # 5-min stratum: fights with both% >= this
PERSIST_FRAC = 0.50       # persistence: >= 50% of jump at +60 min
PERSIST_BARS = 2          # 2 × 30-min bars = 60 min
HORIZONS     = {"same": 0, "+30m": 1, "+1h": 2, "+2h": 4}
GAP_OPEN     = 0.05
GAP_CLOSE    = 0.02
B_BOOT       = 1000
SEED         = 42
CCF_LAGS     = list(range(-6, 7))
CCF_MIN_OBS  = 15         # min co-active bars per fight for CCF

rng = np.random.default_rng(SEED)
print(f"Bootstrap: B={B_BOOT}, seed={SEED}", flush=True)

t0_total = time.time()


# =============================================================================
# HELPERS — markdown table, bootstrap, Fisher-z
# =============================================================================

def md_table(headers: list[str], rows: list[list], col_align: str = "mixed") -> str:
    n = len(headers)
    sep = []
    for h in headers:
        w = max(len(h), 4)
        sep.append(":" + "-" * (w - 1))
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(sep) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def two_stage_boot(fight_stats: np.ndarray, agg_fn, rng, B: int = B_BOOT):
    """
    fight_stats: array shape (n_fights, ...) — one row per fight.
    agg_fn:      callable (fight_stats_array) -> scalar or array.
    Returns:     (observed, ci_lo, ci_hi) — same shape as agg_fn output.
    """
    n = len(fight_stats)
    observed = agg_fn(fight_stats)
    boot_vals = [agg_fn(fight_stats[rng.integers(0, n, size=n)]) for _ in range(B)]
    boot_arr = np.array(boot_vals)
    ci_lo = np.nanpercentile(boot_arr, 2.5, axis=0)
    ci_hi = np.nanpercentile(boot_arr, 97.5, axis=0)
    return observed, ci_lo, ci_hi


def fz(r):
    """Fisher-z transform, with clipping to avoid inf."""
    return np.arctanh(np.clip(r, -0.9999, 0.9999))


def ifz(z):
    """Inverse Fisher-z."""
    return np.tanh(z)


# =============================================================================
# LOAD & PREPARE
# =============================================================================

print("\n[LOAD] reading panel...", flush=True)
t0 = time.time()

df_raw = pd.read_parquet(PANEL)
df_raw["bar_utc"] = pd.to_datetime(df_raw["bar_utc"], utc=True)
df = df_raw[~df_raw["fight_id"].isin(PM_FLIP_EXCLUDE)].copy()
N_FIGHTS = df["fight_id"].nunique()
N_RAW    = df_raw["fight_id"].nunique()
print(f"  {N_RAW} fights in panel → {N_FIGHTS} after excluding {len(PM_FLIP_EXCLUDE)} pm_flip",
      flush=True)

# event_date from fight_id prefix "YYYYMMDD"
df["event_date"] = pd.to_datetime(df["fight_id"].str[:8], format="%Y%m%d", utc=True)

# crosswalk: combined volume for tier
xw = pd.read_parquet(XWALK, columns=["fight_id","kalshi_volume","pm_volume"])
xw = xw[~xw["fight_id"].isin(PM_FLIP_EXCLUDE)].copy()
xw["combined_vol"] = xw["kalshi_volume"].fillna(0) + xw["pm_volume"].fillna(0)
top_thresh  = xw["combined_vol"].quantile(0.90)
xw["tier"]  = np.where(xw["combined_vol"] >= top_thresh, "main_event", "undercard")
tier_map    = xw.set_index("fight_id")["tier"].to_dict()
n_main      = (xw["tier"] == "main_event").sum()
print(f"  Tier threshold (90th pct): {top_thresh:,.0f}  ({n_main} main events)", flush=True)

df["tier"] = df["fight_id"].map(tier_map).fillna("undercard")

# fight-level coverage stats
cov = (df.groupby("fight_id")
         .agg(n_bars     = ("bar_utc",     "count"),
              both_bars  = ("both_traded", "sum"),
              k_n_total  = ("k_n",         "sum"),
              pm_n_total = ("pm_n",        "sum"),
              k_vol_tot  = ("k_vol",       "sum"),
              pm_vol_tot = ("pm_vol",      "sum"))
         .assign(both_pct = lambda x: 100 * x["both_bars"] / x["n_bars"])
         .reset_index())
cov["tier"]       = cov["fight_id"].map(tier_map).fillna("undercard")
cov["event_date"] = pd.to_datetime(cov["fight_id"].str[:8], format="%Y%m%d", utc=True)

hi_cov_fights = set(cov[cov["both_pct"] >= BOTH_PCT_MIN]["fight_id"])
print(f"  Fights with both% >= {BOTH_PCT_MIN}%: {len(hi_cov_fights)}", flush=True)

# gap on co-active bars (both prices available)
gap_bars = df.dropna(subset=["k_last","pm_last"]).copy()
gap_bars["gap"]     = gap_bars["k_last"] - gap_bars["pm_last"]
gap_bars["abs_gap"] = gap_bars["gap"].abs()

print(f"  Loaded in {time.time()-t0:.1f}s", flush=True)


# =============================================================================
# BUILD 30-MIN BARS
# =============================================================================

print("\n[30MIN] aggregating 30-min bars...", flush=True)
t0 = time.time()

chunks30 = []
for fid, grp in df.groupby("fight_id", sort=False):
    s = grp.sort_values("bar_utc").set_index("bar_utc")
    r = pd.DataFrame({
        "k_last":  s["k_last"].resample("30min").last(),
        "pm_last": s["pm_last"].resample("30min").last(),
        "k_n":     s["k_n"].resample("30min").sum(),
        "pm_n":    s["pm_n"].resample("30min").sum(),
        "k_vol":   s["k_vol"].resample("30min").sum(),
        "pm_vol":  s["pm_vol"].resample("30min").sum(),
    })
    r["fight_id"]    = fid
    r["tier"]        = tier_map.get(fid, "undercard")
    r["both_traded"] = (r["k_n"] > 0) & (r["pm_n"] > 0)
    chunks30.append(r.reset_index())

bars30 = pd.concat(chunks30, ignore_index=True)
bars30 = bars30.rename(columns={"index": "bar_utc", "bar_utc": "bar_utc"})
if "index" in bars30.columns:
    bars30 = bars30.rename(columns={"index": "bar_utc"})

co30 = bars30[bars30["both_traded"]].copy()
co30 = co30.sort_values(["fight_id","bar_utc"]).reset_index(drop=True)
co30["dk"]  = co30.groupby("fight_id")["k_last"].diff()
co30["dpm"] = co30.groupby("fight_id")["pm_last"].diff()
print(f"  {len(co30):,} co-active 30-min bars across {co30['fight_id'].nunique()} fights "
      f"({time.time()-t0:.1f}s)", flush=True)


# =============================================================================
# EXHIBIT 1 — SAMPLE & DESCRIPTIVES
# =============================================================================

print("\n[EX1] sample & descriptives...", flush=True)

n_cards    = cov["event_date"].nunique()
date_lo    = cov["event_date"].min().strftime("%Y-%m-%d")
date_hi    = cov["event_date"].max().strftime("%Y-%m-%d")
tot_bars   = int(cov["n_bars"].sum())
tot_both   = int(cov["both_bars"].sum())
k_trades   = int(cov["k_n_total"].sum())
pm_trades  = int(cov["pm_n_total"].sum())
k_notional = float(cov["k_vol_tot"].sum())
pm_notional= float(cov["pm_vol_tot"].sum())

pcts = cov["both_pct"].values
co_share_dist = {p: float(np.percentile(pcts, p))
                 for p in [10, 25, 50, 75, 90]}

tier_counts = cov["tier"].value_counts().to_dict()

# gap level (co-active bars only, both prices non-NaN)
co_gap = gap_bars[gap_bars["both_traded"] & gap_bars["k_last"].notna() & gap_bars["pm_last"].notna()].copy()
gap_overall   = co_gap["gap"]
gap_abs_total = co_gap["abs_gap"]
gap_by_tier   = {t: co_gap[co_gap["tier"] == t]["gap"] for t in ["main_event","undercard"]}

ex1_rows_summary = [
    ["Metric", "Value"],
    ["Fights in panel (raw)", str(N_RAW)],
    ["Fights analyzed (after pm_flip exclusion)", str(N_FIGHTS)],
    ["pm_flip excluded fights", "; ".join(sorted(PM_FLIP_EXCLUDE))],
    ["Fight cards (event dates)", str(n_cards)],
    ["Date range", f"{date_lo} — {date_hi}"],
    ["Total 5-min bars", f"{tot_bars:,}"],
    ["Co-active bars (both venues)", f"{tot_both:,}  ({100*tot_both/tot_bars:.1f}%)"],
    ["Kalshi trades", f"{k_trades:,}"],
    ["Kalshi volume (contracts)", f"{k_notional:,.0f}"],
    ["PM trades", f"{pm_trades:,}"],
    ["PM notional (USDC, ÷1e6 from raw Polygon units)", f"{pm_notional/1e6:,.0f}"],
]

ex1_rows_cov = [
    ["Percentile", "Both% (share of 5-min bars co-active)"],
    ["p10", f"{co_share_dist[10]:.1f}%"],
    ["p25", f"{co_share_dist[25]:.1f}%"],
    ["p50 (median)", f"{co_share_dist[50]:.1f}%"],
    ["p75", f"{co_share_dist[75]:.1f}%"],
    ["p90", f"{co_share_dist[90]:.1f}%"],
]

ex1_rows_tier = [
    ["Tier", "N fights", "Definition"],
    ["main_event", str(tier_counts.get("main_event",0)),
     f"Top 10% by combined K+PM volume (>= {top_thresh:,.0f} contracts+USDC)"],
    ["undercard",  str(tier_counts.get("undercard",0)),  "Remainder"],
]

def gap_row(label, s):
    if len(s) == 0:
        return [label, "n/a", "n/a", "n/a", "n/a"]
    return [label, f"{len(s):,}",
            f"{s.mean():+.4f}", f"{s.median():+.4f}",
            f"{s.abs().mean():.4f}"]

ex1_rows_gap = [
    ["Stratum", "N bars", "Mean gap (K−PM)", "Median gap (K−PM)", "Mean |gap|"],
    gap_row("All co-active bars", gap_overall),
    gap_row("main_event",          gap_by_tier["main_event"]),
    gap_row("undercard",           gap_by_tier["undercard"]),
]

note_gap = ("Gap = K_last − PM_last on co-active bars (both_traded=True, both prices non-NaN). "
            "Positive = Kalshi above PM. Prices in [0, 1] scale (probability); "
            "0.01 = 1 percentage point.")

# CSV
ex1_df = pd.DataFrame({
    "metric": ["n_fights_raw","n_fights_analyzed","n_cards","date_lo","date_hi",
                "tot_bars","tot_both_bars","k_trades","k_vol_contracts","pm_trades",
                "pm_notional_usdc","co_pct_p10","co_pct_p25","co_pct_p50",
                "co_pct_p75","co_pct_p90","n_main_event","n_undercard",
                "gap_mean_all","gap_median_all","abs_gap_mean_all",
                "gap_mean_main","gap_mean_undercard"],
    "value":  [N_RAW, N_FIGHTS, n_cards, date_lo, date_hi,
               tot_bars, tot_both, k_trades, k_notional, pm_trades,
               pm_notional,
               co_share_dist[10], co_share_dist[25], co_share_dist[50],
               co_share_dist[75], co_share_dist[90],
               tier_counts.get("main_event",0), tier_counts.get("undercard",0),
               float(gap_overall.mean()), float(gap_overall.median()),
               float(gap_abs_total.mean()),
               float(gap_by_tier["main_event"].mean()) if len(gap_by_tier["main_event"]) else float("nan"),
               float(gap_by_tier["undercard"].mean())  if len(gap_by_tier["undercard"])  else float("nan")],
})
ex1_df.to_csv(OUT_DIR / "ex1_sample.csv", index=False)

ex1_md = f"""## Exhibit 1 — Sample & Descriptives
**Source:** `data/clean/phase2_full_panel.parquet`
**Generated:** code/exhibit_freeze.py

### 1A — Overall sample

{md_table(ex1_rows_summary[0], ex1_rows_summary[1:])}

### 1B — Co-active coverage distribution (share of 5-min bars where both venues traded)

{md_table(ex1_rows_cov[0], ex1_rows_cov[1:])}

Fights in 5-min stratum (both% ≥ {BOTH_PCT_MIN:.0f}%): **{len(hi_cov_fights)}**

### 1C — Fights by tier

{md_table(ex1_rows_tier[0], ex1_rows_tier[1:])}

### 1D — Level gap K − PM (co-active bars, prices in [0,1])

{md_table(ex1_rows_gap[0], ex1_rows_gap[1:])}

*{note_gap}*
"""
(OUT_DIR / "ex1_sample.md").write_text(ex1_md, encoding="utf-8")
print(f"  saved ex1", flush=True)


# =============================================================================
# EXHIBIT 2 — CROSS-CORRELATION (Fisher-z averaged, two-stage bootstrap CI)
# =============================================================================

print("\n[EX2] cross-correlation...", flush=True)
t0 = time.time()

def fight_ccf(grp: pd.DataFrame, lags: list[int], min_obs: int = CCF_MIN_OBS
              ) -> np.ndarray | None:
    """
    Compute per-fight CCF at each lag.
    Convention: corr(dK_t, dPM_{t+k}).  k>0 → K leads.
    Returns Fisher-z array of shape (len(lags),), or None if too sparse.
    """
    grp = grp.sort_values("bar_utc").reset_index(drop=True)
    dk  = grp["k_last"].diff().values
    dpm = grp["pm_last"].diff().values

    zs = np.full(len(lags), np.nan)
    for li, k in enumerate(lags):
        if k >= 0:
            dk_  = dk[:-k]    if k > 0 else dk
            dpm_ = dpm[k:]    if k > 0 else dpm
        else:
            # k negative: dPM leads. dPM.shift(-k) at position t gives dPM[t+k]
            # For k=-2: dPM.shift(2)[t] = dPM[t-2] → we want dPM[t+k]=dPM[t-2]
            # Use: dk_ = dk[-k:], dpm_ = dpm[:k] (k is negative, so :k truncates from end)
            dk_  = dk[(-k):]
            dpm_ = dpm[:k]    # k negative, so this is dpm[:k] which drops last |k| elements

        mask = np.isfinite(dk_) & np.isfinite(dpm_)
        if mask.sum() < min_obs:
            continue
        d1, d2 = dk_[mask], dpm_[mask]
        if d1.std() < 1e-12 or d2.std() < 1e-12:
            continue
        r = float(np.corrcoef(d1, d2)[0, 1])
        zs[li] = fz(r)
    return zs if not np.all(np.isnan(zs)) else None


def run_ccf(panel_sub: pd.DataFrame, label: str) -> dict:
    """Run CCF for given panel subset. Returns dict with rho, ci_lo, ci_hi."""
    fight_ids = sorted(panel_sub["fight_id"].unique())
    per_fight = []
    for fid in fight_ids:
        grp = panel_sub[panel_sub["fight_id"] == fid]
        zs  = fight_ccf(grp, CCF_LAGS)
        if zs is not None:
            per_fight.append(zs)

    if not per_fight:
        return {"label": label, "n_fights": 0, "lags": CCF_LAGS,
                "rho": [np.nan]*len(CCF_LAGS),
                "ci_lo": [np.nan]*len(CCF_LAGS),
                "ci_hi": [np.nan]*len(CCF_LAGS)}

    mat = np.array(per_fight)   # shape (n_fights, n_lags)
    n_fights = len(mat)

    def agg(m):
        return np.nanmean(m, axis=0)   # Fisher-z mean

    obs_z, ci_lo_z, ci_hi_z = two_stage_boot(mat, agg, rng)
    rho_obs  = ifz(obs_z)
    rho_lo   = ifz(ci_lo_z)
    rho_hi   = ifz(ci_hi_z)

    return {"label": label, "n_fights": n_fights, "lags": CCF_LAGS,
            "rho": rho_obs.tolist(), "ci_lo": rho_lo.tolist(), "ci_hi": rho_hi.tolist()}


# 5-min stratum: co-active bars, fights with both% >= 25%
df5_sub = df[df["fight_id"].isin(hi_cov_fights)].copy()
df5_sub = df5_sub[df5_sub["both_traded"] & df5_sub["k_last"].notna() & df5_sub["pm_last"].notna()]
ccf5    = run_ccf(df5_sub, f"5-min co-active (both%≥{BOTH_PCT_MIN:.0f}%)")

# 30-min stratum: all 178 fights, co-active 30-min bars
ccf30   = run_ccf(co30, "30-min co-active (all fights)")

print(f"  5-min:  {ccf5['n_fights']} fights contributing",  flush=True)
print(f"  30-min: {ccf30['n_fights']} fights contributing", flush=True)

def lead_label(k):
    if k > 0: return "K leads"
    if k < 0: return "PM leads"
    return "contemporaneous"

def sig_flag(lo, hi):
    return "*" if (lo > 0 or hi < 0) else ""

ex2_rows = [["lag", "rho_5min", "CI_95_5min", "sig_5", "rho_30min", "CI_95_30min", "sig_30", "lead"]]
for i, k in enumerate(CCF_LAGS):
    r5   = ccf5["rho"][i];   lo5 = ccf5["ci_lo"][i];   hi5 = ccf5["ci_hi"][i]
    r30  = ccf30["rho"][i];  lo30 = ccf30["ci_lo"][i]; hi30 = ccf30["ci_hi"][i]
    ex2_rows.append([
        f"{k:+d}",
        f"{r5:+.4f}"  if np.isfinite(r5)  else "n/a",
        f"[{lo5:+.4f}, {hi5:+.4f}]" if np.isfinite(lo5) else "n/a",
        sig_flag(lo5, hi5),
        f"{r30:+.4f}" if np.isfinite(r30) else "n/a",
        f"[{lo30:+.4f}, {hi30:+.4f}]" if np.isfinite(lo30) else "n/a",
        sig_flag(lo30, hi30),
        lead_label(k),
    ])

# CSV
ex2_df = pd.DataFrame({
    "lag":       CCF_LAGS,
    "rho_5min":  ccf5["rho"], "ci_lo_5min": ccf5["ci_lo"], "ci_hi_5min": ccf5["ci_hi"],
    "rho_30min": ccf30["rho"],"ci_lo_30min":ccf30["ci_lo"],"ci_hi_30min":ccf30["ci_hi"],
    "lead":      [lead_label(k) for k in CCF_LAGS],
})
ex2_df.to_csv(OUT_DIR / "ex2_ccf.csv", index=False)

ex2_md = f"""## Exhibit 2 — Cross-Venue Cross-Correlation
**Lead convention:** `corr(dK_t, dPM_{{t+k}})`. k > 0 → K leads (K moves now, PM adjusts later). k < 0 → PM leads.
**CI:** 95% two-stage bootstrap (resample fights, B={B_BOOT}, seed={SEED}).
**`*`** = 95% CI excludes zero.

5-min stratum: {ccf5['n_fights']} fights (both% ≥ {BOTH_PCT_MIN:.0f}%).
30-min stratum: {ccf30['n_fights']} fights (all {N_FIGHTS}).

{md_table(ex2_rows[0], ex2_rows[1:])}
"""
(OUT_DIR / "ex2_ccf.md").write_text(ex2_md, encoding="utf-8")
print(f"  saved ex2  ({time.time()-t0:.1f}s)", flush=True)


# =============================================================================
# EXHIBIT 3 — JUMP ANATOMY (30-min stratum)
# =============================================================================

print("\n[EX3] jump anatomy (30-min)...", flush=True)
t0 = time.time()


def three_bucket(co_df, a_col, b_col, thresh):
    """Per-fight same/zero/opposite rates; also aggregate."""
    per_fight_same = []
    per_fight_opp  = []
    agg_n = agg_same = agg_zero = agg_opp = 0
    for fid, grp in co_df.groupby("fight_id", sort=False):
        jumps = grp[grp[a_col].abs() >= thresh].dropna(subset=[a_col, b_col])
        if len(jumps) == 0:
            continue
        signs = np.sign(jumps[a_col].values)
        bsign = signs * jumps[b_col].values
        n  = len(jumps)
        ns = int((bsign >  0).sum())
        nz = int((bsign == 0).sum())
        no = int((bsign <  0).sum())
        agg_n += n; agg_same += ns; agg_zero += nz; agg_opp += no
        per_fight_same.append(ns / n)
        per_fight_opp.append(no / n)
    return {
        "n": agg_n, "n_same": agg_same, "n_zero": agg_zero, "n_opp": agg_opp,
        "pct_same": agg_same/agg_n*100 if agg_n else 0,
        "pct_zero": agg_zero/agg_n*100 if agg_n else 0,
        "pct_opp":  agg_opp/agg_n*100  if agg_n else 0,
        "per_fight_same": np.array(per_fight_same),
        "per_fight_opp":  np.array(per_fight_opp),
    }


def bucket_diff_ci(r_k, r_pm, rng, B=B_BOOT):
    """
    Bootstrap CI for difference in same-dir rate: K→PM vs PM→K.
    Staged by fight: each fight contributes its own same-rate.
    """
    n_k  = len(r_k["per_fight_same"])
    n_pm = len(r_pm["per_fight_same"])
    obs_diff = r_k["pct_same"] - r_pm["pct_same"]
    boot = []
    for _ in range(B):
        bk  = r_k["per_fight_same"][rng.integers(0, max(n_k, 1), size=max(n_k, 1))]
        bpm = r_pm["per_fight_same"][rng.integers(0, max(n_pm, 1), size=max(n_pm, 1))]
        boot.append((bk.mean() - bpm.mean()) * 100)
    ci_lo = float(np.percentile(boot, 2.5))
    ci_hi = float(np.percentile(boot, 97.5))
    return obs_diff, ci_lo, ci_hi


def propagation_table(co_df, a_col, b_col, price_a_col, horizons, persist_bars):
    """
    Compute per-fight mean aligned B response per (class, horizon).
    Returns: dict {class: {horizon: array-per-fight}}
    """
    per_fight   = {"PERSISTENT": {h: [] for h in horizons},
                   "TRANSIENT":  {h: [] for h in horizons}}
    event_lists = {"PERSISTENT": {h: [] for h in horizons},
                   "TRANSIENT":  {h: [] for h in horizons}}

    for fid, grp in co_df.groupby("fight_id", sort=False):
        grp = grp.sort_values("bar_utc").reset_index(drop=True)
        a_ret   = grp[a_col].values
        b_ret   = grp[b_col].values
        a_price = grp[price_a_col].values
        n = len(grp)
        fight_cells = {"PERSISTENT": {h: [] for h in horizons},
                       "TRANSIENT":  {h: [] for h in horizons}}

        for i in range(1, n):
            ra = a_ret[i]
            if not (np.isfinite(ra) and abs(ra) >= JUMP_THRESH):
                continue
            if i + persist_bars >= n:
                continue
            sign = np.sign(ra)
            pre_price  = a_price[i - 1]
            post_price = a_price[i + persist_bars]
            if not (np.isfinite(pre_price) and np.isfinite(post_price)):
                continue
            cumul_a = post_price - pre_price
            cls = "PERSISTENT" if (sign * cumul_a) >= PERSIST_FRAC * abs(ra) else "TRANSIENT"

            for hlbl, hbars in horizons.items():
                if hbars == 0:
                    bv = b_ret[i]
                    val = sign * bv if np.isfinite(bv) else np.nan
                else:
                    end = i + 1 + hbars
                    if end > n:
                        val = np.nan
                    else:
                        chunk = b_ret[i + 1:end]
                        nfin = np.sum(np.isfinite(chunk))
                        val = sign * np.nansum(chunk) if nfin >= max(1, hbars // 2) else np.nan
                fight_cells[cls][hlbl].append(val)
                event_lists[cls][hlbl].append(val)   # per-event, for point estimates

        for cls in per_fight:
            for h in horizons:
                vals = fight_cells[cls][h]
                per_fight[cls][h].append(
                    np.nanmean(vals) if any(np.isfinite(v) for v in vals) else np.nan
                )

    for cls in per_fight:
        for h in horizons:
            per_fight[cls][h] = np.array(per_fight[cls][h], dtype=float)
    return per_fight, event_lists


def prop_cell_ci(pf_arr, rng, B=B_BOOT):
    """Bootstrap CI on per-fight means (two-stage)."""
    valid = pf_arr[np.isfinite(pf_arr)]
    if len(valid) < 2:
        return float(np.nanmean(pf_arr)) if len(valid) else np.nan, np.nan, np.nan
    boot = [valid[rng.integers(0, len(valid), size=len(valid))].mean() for _ in range(B)]
    return float(valid.mean()), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


# Panel A: 3c threshold
bk3  = three_bucket(co30, "dk",  "dpm", JUMP_THRESH)
bpm3 = three_bucket(co30, "dpm", "dk",  JUMP_THRESH)
diff3, ci_lo3, ci_hi3 = bucket_diff_ci(bk3, bpm3, rng)

# Panel B: 5c threshold
bk5  = three_bucket(co30, "dk",  "dpm", JUMP_BIG)
bpm5 = three_bucket(co30, "dpm", "dk",  JUMP_BIG)
diff5, ci_lo5, ci_hi5 = bucket_diff_ci(bk5, bpm5, rng)

# Panel C: persistent / transient propagation (K→PM and PM→K)
# per_fight → bootstrap; event_lists → per-event point estimates matching QA
hlbls = list(HORIZONS.keys())
prop_k_pf,  prop_k_ev  = propagation_table(co30, "dk",  "dpm", "k_last",  HORIZONS, PERSIST_BARS)
prop_pm_pf, prop_pm_ev = propagation_table(co30, "dpm", "dk",  "pm_last", HORIZONS, PERSIST_BARS)


def prop_row(lbl, cname, pf_dict, ev_dict, cls, hlbls, rng):
    """
    Point estimate = per-event mean (matches QA).
    CI = two-stage bootstrap on per-fight means.
    N = number of events with finite 'same' response.
    """
    n_events = sum(1 for v in ev_dict[cls]["same"] if np.isfinite(v))
    cells = []
    for h in hlbls:
        evs  = [v for v in ev_dict[cls][h] if np.isfinite(v)]
        obs  = float(np.mean(evs)) if evs else np.nan
        _, lo, hi = prop_cell_ci(pf_dict[cls][h], rng)
        cells.append(f"{obs:+.4f} [{lo:+.4f},{hi:+.4f}]" if np.isfinite(obs) else "n/a")
    return [lbl, cname, str(n_events)] + cells

ex3_rows_a = [
    ["Direction", "N jumps", "same (%)", "zero (%)", "opposite (%)"],
    ["K→PM (≥3¢)",
     str(bk3["n"]),
     f"{bk3['n_same']} ({bk3['pct_same']:.1f}%)",
     f"{bk3['n_zero']} ({bk3['pct_zero']:.1f}%)",
     f"{bk3['n_opp']} ({bk3['pct_opp']:.1f}%)"],
    ["PM→K (≥3¢)",
     str(bpm3["n"]),
     f"{bpm3['n_same']} ({bpm3['pct_same']:.1f}%)",
     f"{bpm3['n_zero']} ({bpm3['pct_zero']:.1f}%)",
     f"{bpm3['n_opp']} ({bpm3['pct_opp']:.1f}%)"],
    ["K→PM same-rate minus PM→K same-rate",
     "—",
     f"{diff3:+.1f}pp  95% CI [{ci_lo3:+.1f}, {ci_hi3:+.1f}]pp",
     "—", "—"],
]

ex3_rows_b = [
    ["Direction", "N jumps", "same (%)", "zero (%)", "opposite (%)"],
    ["K→PM (≥5¢)",
     str(bk5["n"]),
     f"{bk5['n_same']} ({bk5['pct_same']:.1f}%)",
     f"{bk5['n_zero']} ({bk5['pct_zero']:.1f}%)",
     f"{bk5['n_opp']} ({bk5['pct_opp']:.1f}%)"],
    ["PM→K (≥5¢)",
     str(bpm5["n"]),
     f"{bpm5['n_same']} ({bpm5['pct_same']:.1f}%)",
     f"{bpm5['n_zero']} ({bpm5['pct_zero']:.1f}%)",
     f"{bpm5['n_opp']} ({bpm5['pct_opp']:.1f}%)"],
    ["K→PM same-rate minus PM→K same-rate",
     "—",
     f"{diff5:+.1f}pp  95% CI [{ci_lo5:+.1f}, {ci_hi5:+.1f}]pp",
     "—", "—"],
]

ex3_rows_c = [["Direction", "Class", "N"] + [f"{h} (mean [95% CI])" for h in hlbls]]
for lbl, pf, ev in [("K\u2192PM", prop_k_pf, prop_k_ev), ("PM\u2192K", prop_pm_pf, prop_pm_ev)]:
    for cname in ["PERSISTENT", "TRANSIENT"]:
        ex3_rows_c.append(prop_row(lbl, cname, pf, ev, cname, hlbls, rng))

# CSV
ex3_records = []
for direction, bdict in [("K→PM_3c", bk3), ("PM→K_3c", bpm3),
                          ("K→PM_5c", bk5), ("PM→K_5c", bpm5)]:
    ex3_records.append({"direction": direction, "threshold": direction[-2:],
                         "n": bdict["n"],
                         "same_n": bdict["n_same"], "same_pct": bdict["pct_same"],
                         "zero_n": bdict["n_zero"], "zero_pct": bdict["pct_zero"],
                         "opp_n":  bdict["n_opp"],  "opp_pct":  bdict["pct_opp"]})
ex3_df = pd.DataFrame(ex3_records)
ex3_df.to_csv(OUT_DIR / "ex3_jump.csv", index=False)

ex3_md = f"""## Exhibit 3 — Jump Anatomy (30-min stratum, {N_FIGHTS} fights)
**Jump:** |ret| ≥ threshold on co-active 30-min bars.
**B's response:** B's return on same bar, signed by A's direction.
**Bootstrap:** B={B_BOOT}, seed={SEED}, two-stage by fight.

### Panel A — Three-bucket decomposition (≥ 3¢ jumps)

{md_table(ex3_rows_a[0], ex3_rows_a[1:])}

### Panel B — Three-bucket decomposition (≥ 5¢ jumps)

{md_table(ex3_rows_b[0], ex3_rows_b[1:])}

### Panel C — Persistent vs transient propagation (≥ 3¢, 30-min bars)
PERSISTENT = A's price still ≥ 50% of jump after 60 min (2 bars). Values = B's aligned cumulative return. CIs two-stage bootstrap by fight.

{md_table(ex3_rows_c[0], ex3_rows_c[1:])}
"""
(OUT_DIR / "ex3_jump.md").write_text(ex3_md, encoding="utf-8")
print(f"  saved ex3  ({time.time()-t0:.1f}s)", flush=True)


# =============================================================================
# EXHIBIT 4 — GAP CLOSURE
# =============================================================================

print("\n[EX4] gap closure episodes...", flush=True)
t0 = time.time()

all_bars = df.copy()
all_bars = all_bars.sort_values(["fight_id","bar_utc"]).reset_index(drop=True)
all_bars["gap"]     = all_bars["k_last"] - all_bars["pm_last"]
all_bars["abs_gap"] = all_bars["gap"].abs()

episodes = []
for fid, grp in all_bars.groupby("fight_id", sort=False):
    grp = grp.sort_values("bar_utc").reset_index(drop=True)
    abs_g    = grp["abs_gap"].values
    times    = grp["bar_utc"].values
    k_n_arr  = grp["k_n"].values
    pm_n_arr = grp["pm_n"].values
    valid    = grp["k_last"].notna().values & grp["pm_last"].notna().values
    n = len(grp)

    in_ep = False
    ep_start_i = None
    ep_bars_k = []; ep_bars_pm = []

    for i in range(n):
        if not valid[i]:
            if in_ep:
                ep_bars_k.append(0); ep_bars_pm.append(0)
            continue
        ag = abs_g[i]

        if not in_ep:
            # check if this bar opens an episode
            prev_ag = None
            for j in range(i - 1, -1, -1):
                if valid[j]:
                    prev_ag = abs_g[j]; break
            if ag >= GAP_OPEN and (prev_ag is None or prev_ag < GAP_OPEN):
                in_ep = True; ep_start_i = i
                ep_bars_k  = [int(k_n_arr[i])]
                ep_bars_pm = [int(pm_n_arr[i])]
        else:
            ep_bars_k.append(int(k_n_arr[i]))
            ep_bars_pm.append(int(pm_n_arr[i]))

            if ag <= GAP_CLOSE:
                dur_min = (pd.Timestamp(times[i]) - pd.Timestamp(times[ep_start_i])
                           ).total_seconds() / 60
                k_active  = any(v > 0 for v in ep_bars_k)
                pm_active = any(v > 0 for v in ep_bars_pm)
                ep_type   = "ACTIVE" if (k_active and pm_active) else "STALE-SIDE"
                episodes.append({
                    "fight_id":     fid,
                    "tier":         tier_map.get(fid, "undercard"),
                    "duration_min": dur_min,
                    "censored":     False,
                    "type":         ep_type,
                })
                in_ep = False; ep_bars_k = []; ep_bars_pm = []

    if in_ep:
        k_active  = any(v > 0 for v in ep_bars_k)
        pm_active = any(v > 0 for v in ep_bars_pm)
        ep_type   = "ACTIVE" if (k_active and pm_active) else "STALE-SIDE"
        episodes.append({
            "fight_id":     fid,
            "tier":         tier_map.get(fid, "undercard"),
            "duration_min": np.nan,
            "censored":     True,
            "type":         ep_type,
        })

eps_df = pd.DataFrame(episodes)

def gap_summary(sub, rng, B=B_BOOT):
    if len(sub) == 0:
        return {}
    n_total  = len(sub)
    closed   = sub[~sub["censored"]]
    n_closed = len(closed)
    n_cens   = n_total - n_closed

    if n_closed == 0:
        return {"n": n_total, "n_closed": n_closed, "n_censored": n_cens,
                "median_min": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
                "lt30": np.nan, "lt2h": np.nan, "lt6h": np.nan}

    durs  = closed["duration_min"].values

    # Two-stage bootstrap: resample episodes (all from potentially multiple fights)
    # Here we treat each episode as the unit of analysis
    obs_med = float(np.median(durs))
    boot = [np.median(durs[rng.integers(0, len(durs), size=len(durs))]) for _ in range(B)]
    ci_lo = float(np.percentile(boot, 2.5))
    ci_hi = float(np.percentile(boot, 97.5))

    lt30 = float((durs < 30).mean())
    lt2h = float((durs < 120).mean())
    lt6h = float((durs < 360).mean())
    return {"n": n_total, "n_closed": n_closed, "n_censored": n_cens,
            "median_min": obs_med, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "lt30": lt30, "lt2h": lt2h, "lt6h": lt6h}


active_eps     = eps_df[eps_df["type"] == "ACTIVE"]
stale_eps      = eps_df[eps_df["type"] == "STALE-SIDE"]
active_main    = active_eps[active_eps["tier"] == "main_event"]
active_under   = active_eps[active_eps["tier"] == "undercard"]

s_main  = gap_summary(active_main,  rng)
s_under = gap_summary(active_under, rng)
s_stale = gap_summary(stale_eps,    rng)

def fmt_row(label, ep_type, tier, s):
    if not s:
        return [label, ep_type, tier, "0", "0", "0", "n/a", "n/a", "n/a", "n/a", "n/a"]
    med_str = (f"{s['median_min']:.0f} [{s['ci_lo']:.0f},{s['ci_hi']:.0f}]"
               if np.isfinite(s.get("median_min", np.nan)) else "n/a")
    return [label, ep_type, tier,
            str(s["n"]), str(s["n_closed"]), str(s["n_censored"]),
            med_str,
            f"{s['lt30']:.0%}" if np.isfinite(s.get("lt30",np.nan)) else "n/a",
            f"{s['lt2h']:.0%}" if np.isfinite(s.get("lt2h",np.nan)) else "n/a",
            f"{s['lt6h']:.0%}" if np.isfinite(s.get("lt6h",np.nan)) else "n/a",
            f"N={s['n_closed']}"]

ex4_rows = [
    ["Stratum", "Type", "Tier", "N ep", "N closed", "N censored",
     "Median min [95% CI]", "<30m", "<2h", "<6h", "Note"],
    fmt_row("ACTIVE",     "ACTIVE",     "main_event", s_main),
    fmt_row("ACTIVE",     "ACTIVE",     "undercard",  s_under),
    fmt_row("STALE-SIDE", "STALE-SIDE", "all",        s_stale),
]

eps_df.to_csv(OUT_DIR / "ex4_gap.csv", index=False)

ex4_md = f"""## Exhibit 4 — Gap Closure
**Gap episodes:** |K_last − PM_last| crosses {GAP_OPEN*100:.0f}¢ → closes ≤ {GAP_CLOSE*100:.0f}¢ (prices in [0,1]).
**ACTIVE:** both venues trade during episode.  **STALE-SIDE:** one venue has zero trades throughout.
**Tier:** main_event = top-decile combined volume (N={n_main}).
**Bootstrap:** median CI = two-stage resample of episodes, B={B_BOOT}, seed={SEED}.

{md_table(ex4_rows[0], ex4_rows[1:])}
"""
(OUT_DIR / "ex4_gap.md").write_text(ex4_md, encoding="utf-8")
print(f"  saved ex4  ({time.time()-t0:.1f}s)", flush=True)


# =============================================================================
# EXHIBIT 5 — OWN-FLOW SUMMARY (Phase 1 results, no recomputation)
# =============================================================================

print("\n[EX5] own-flow summary (Phase 1 hardcoded)...", flush=True)

# Numbers from: qa/phase1_quintile_sort.md (training) and
#               qa/trackB_confirmatory_score.md (confirmatory)
# Fee: 7% schedule, P=0.44 → round-trip 3.45 ct
ex5_rows_main = [
    ["Sample", "OFI variant", "Q5-Q1 lag-1 (ct)", "SE", "t", "p", "n_cards"],
    ["Training (Apr 2026+, 8 cards)", "z-OFI",        "−0.12", "0.031", "−3.91", "0.0001", "8"],
    ["Training (Apr 2026+, 8 cards)", "volume-scaled", "−0.34", "0.054", "−6.34", "<0.001", "8"],
    ["Holdout (2 cards)",             "z-OFI",        "+0.04", "0.116", "+0.33", "0.74",   "2"],
    ["Holdout (2 cards)",             "volume-scaled", "−0.71", "0.342", "−2.08", "0.037",  "2"],
    ["Confirmatory (Feb–Nov 2025, 26 cards)", "volume-scaled (PRIMARY)", "−1.13", "0.179", "−6.29", "<0.001", "26"],
    ["Confirmatory (Feb–Nov 2025, 26 cards)", "z-OFI (secondary)",       "−0.14", "0.107", "−1.27", "0.204",  "26"],
]

ex5_rows_verdict = [
    ["Phase", "Criterion", "Verdict"],
    ["Training",       "OFI reversal (sign validation)", "FOUND — both variants negative"],
    ["Holdout",        "Both Q5-Q1 spreads negative",    "NOT CONFIRMED — z-OFI positive"],
    ["Confirmatory",   "vol-scaled < 0 AND |t| ≥ 2",    "**CONFIRM** (t = −6.29)"],
]

ex5_fee_row = [
    ["Kalshi taker fee", "Round-trip at median P=0.44", "Round-trip (ct)"],
    ["7% × P × (1-P) per side", "2 × 7% × 0.44 × 0.56", "3.45 ct"],
]

ex5_df = pd.DataFrame({
    "sample":     ["training_z","training_vol","holdout_z","holdout_vol",
                   "confirm_vol","confirm_z"],
    "ofi_variant":["z-OFI","volume-scaled","z-OFI","volume-scaled",
                   "volume-scaled","z-OFI"],
    "spread_ct":  [-0.12,-0.34,+0.04,-0.71,-1.13,-0.14],
    "se":         [0.031,0.054,0.116,0.342,0.179,0.107],
    "t":          [-3.91,-6.34,+0.33,-2.08,-6.29,-1.27],
    "n_cards":    [8,8,2,2,26,26],
    "fee_rt_ct":  [3.45]*6,
})
ex5_df.to_csv(OUT_DIR / "ex5_ownflow.csv", index=False)

ex5_md = f"""## Exhibit 5 — Within-Venue Order Flow (Phase 1 Summary)
**Source:** `qa/phase1_quintile_sort.md`, `qa/trackB_phase1_holdout_score.md`,
`qa/trackB_confirmatory_score.md`.  No recomputation — values frozen from QA files.
**Construction:** 5-min bars, taker_side OFI, quintile sort on lag-1 forward return (cents),
SE clustered by fight card.

### 5A — Quintile sort Q5-Q1 spread (lag-1)

{md_table(ex5_rows_main[0], ex5_rows_main[1:])}

### 5B — Verdict sequence

{md_table(ex5_rows_verdict[0], ex5_rows_verdict[1:])}

### 5C — Fee benchmark

{md_table(ex5_fee_row[0], ex5_fee_row[1:])}

Confirmatory registration: `osf/trackB_confirmatory_registration.md`.
Closeout: `osf/phase1_closeout.md`.
"""
(OUT_DIR / "ex5_ownflow.md").write_text(ex5_md, encoding="utf-8")
print(f"  saved ex5", flush=True)


# =============================================================================
# MANIFEST
# =============================================================================

elapsed = time.time() - t0_total
print(f"\n[MANIFEST] total elapsed: {elapsed:.1f}s", flush=True)

manifest = f"""# Exhibit Manifest
**Generated:** code/exhibit_freeze.py
**Bootstrap:** B={B_BOOT}, seed={SEED}, two-stage (per-fight stats → resample fight rows)
**Total runtime:** {elapsed:.1f}s

| Exhibit | Files | Source panel | Source QA | Description |
|:--------|:------|:------------|:----------|:------------|
| 1 | ex1_sample.{{csv,md}} | phase2_full_panel.parquet | — | Sample counts, coverage, gap levels |
| 2 | ex2_ccf.{{csv,md}} | phase2_full_panel.parquet | qa/phase2_prototype_leadlag.md | CCF k=−6..+6, two strata, Fisher-z |
| 3 | ex3_jump.{{csv,md}} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md, qa/phase2_asymmetry_robustness.md | Jump anatomy: 3-bucket + persistent/transient |
| 4 | ex4_gap.{{csv,md}} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md | Gap closure by tier |
| 5 | ex5_ownflow.{{csv,md}} | — (hardcoded from QA) | qa/phase1_quintile_sort.md, qa/trackB_phase1_holdout_score.md, qa/trackB_confirmatory_score.md | Phase 1 OFI quintile sort summary |

## Key parameters
- pm_flip exclusions: {sorted(PM_FLIP_EXCLUDE)}
- Jump threshold (Panel A): {JUMP_THRESH*100:.0f}¢
- Jump threshold (Panel B): {JUMP_BIG*100:.0f}¢
- Persistence: ≥{PERSIST_FRAC*100:.0f}% of jump survives 60 min (2 bars at 30-min)
- Gap open: {GAP_OPEN*100:.0f}¢ → close: {GAP_CLOSE*100:.0f}¢
- Tier: main_event = top {100*(1-0.90):.0f}th decile by combined K+PM volume (≥{top_thresh:,.0f})
- 5-min stratum: fights with co-active% ≥ {BOTH_PCT_MIN:.0f}% ({len(hi_cov_fights)} fights)
- 30-min stratum: all {N_FIGHTS} fights
"""
(OUT_DIR / "MANIFEST.md").write_text(manifest, encoding="utf-8")
print(f"  saved MANIFEST.md", flush=True)
print(f"\nAll exhibits → {OUT_DIR}", flush=True)
