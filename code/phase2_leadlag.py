"""
phase2_leadlag.py
=================
Lead-lag analysis between Kalshi and Polymarket UFC fight markets.

Table 1 — CCF at 5-min (both%>=25% fights) and 15-min (all 20 fights).
Table 2 — Jump response (|ret| >= 3 cents) cross-venue propagation.

Convention: corr(dK_t, dPM_{t+k})
  k > 0  => Kalshi leads  (K moves now, PM moves later)
  k < 0  => PM leads      (PM moves earlier, K moves later)
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT  = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
PANEL = ROOT / "data/clean/phase2_prototype_panel.parquet"
QA    = ROOT / "qa/phase2_prototype_leadlag.md"
QA.parent.mkdir(parents=True, exist_ok=True)

# ── load ───────────────────────────────────────────────────────────────────────
df = pd.read_parquet(PANEL)
df["bar_utc"] = pd.to_datetime(df["bar_utc"], utc=True)

# ── fight coverage summary (for stratum filter) ────────────────────────────────
cov = (
    df.groupby("fight_id")
    .agg(
        total_bars=("both_traded", "count"),
        both_bars=("both_traded", "sum"),
    )
    .assign(both_pct=lambda x: 100 * x["both_bars"] / x["total_bars"])
)
hi_cov = cov[cov["both_pct"] >= 25].index.tolist()
print(f"Fights with both% >= 25%: {len(hi_cov)} / {len(cov)}")
print(cov.sort_values("both_pct", ascending=False).to_string())
print()

# ══════════════════════════════════════════════════════════════════════════════
# Helper: CCF for a single fight's return series
# ══════════════════════════════════════════════════════════════════════════════
MAX_LAG = 6   # k = -MAX_LAG .. +MAX_LAG


def compute_returns(sub: pd.DataFrame, price_col: str) -> pd.Series:
    """First difference of last-price on the given sub-df, indexed by bar_utc."""
    return sub.set_index("bar_utc")[price_col].diff()


def ccf_one_fight(dk: pd.Series, dpm: pd.Series, max_lag: int = MAX_LAG):
    """
    Pearson corr(dK_t, dPM_{t+k}) for k = -max_lag..+max_lag.
    Aligns by index, drops NaN pairs.
    Returns array of length 2*max_lag+1, k = -max_lag .. +max_lag
    and array of N used at each lag.
    """
    lags = range(-max_lag, max_lag + 1)
    rhos, ns = [], []
    for k in lags:
        if k >= 0:
            a = dk.values[: len(dk) - k] if k > 0 else dk.values
            b = dpm.values[k:] if k > 0 else dpm.values
        else:  # k < 0 => shift PM back
            k_abs = -k
            a = dk.values[k_abs:]
            b = dpm.values[: len(dpm) - k_abs]
        # align length
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
        mask = np.isfinite(a) & np.isfinite(b)
        if mask.sum() < 10:
            rhos.append(np.nan)
            ns.append(mask.sum())
        else:
            rhos.append(np.corrcoef(a[mask], b[mask])[0, 1])
            ns.append(mask.sum())
    return np.array(rhos), np.array(ns)


# ── Fisher-z averaging with simple stationary-bootstrap CI ────────────────────
def fisher_avg_ci(rho_list, n_list, alpha=0.05, n_boot=1000, block_len=5):
    """
    Fisher-z average of rho values, bootstrap CI over fights.
    rho_list: list of arrays (one per fight)
    n_list:   list of arrays (N at each lag for each fight)
    Returns: mean_rho, ci_lo, ci_hi  (all arrays of length 2*MAX_LAG+1)
    """
    rho_mat = np.array(rho_list)   # shape (n_fights, n_lags)
    n_mat   = np.array(n_list)

    # weighted Fisher-z average (weight = N_i)
    z_mat = np.arctanh(np.clip(rho_mat, -0.9999, 0.9999))
    w_mat = np.where(np.isfinite(z_mat), n_mat, 0.0)
    w_sum = w_mat.sum(axis=0)
    z_avg = (z_mat * w_mat).sum(axis=0) / np.where(w_sum > 0, w_sum, np.nan)
    rho_avg = np.tanh(z_avg)

    # simple stationary bootstrap over fights (rows)
    n_fights = rho_mat.shape[0]
    boot_avgs = []
    rng = np.random.default_rng(42)
    for _ in range(n_boot):
        idx = rng.integers(0, n_fights, size=n_fights)
        bz  = z_mat[idx]
        bw  = w_mat[idx]
        bws = bw.sum(axis=0)
        bz_avg = (bz * bw).sum(axis=0) / np.where(bws > 0, bws, np.nan)
        boot_avgs.append(np.tanh(bz_avg))
    boot_avgs = np.array(boot_avgs)
    ci_lo = np.nanpercentile(boot_avgs, 100 * alpha / 2, axis=0)
    ci_hi = np.nanpercentile(boot_avgs, 100 * (1 - alpha / 2), axis=0)
    return rho_avg, ci_lo, ci_hi, rho_mat


# ══════════════════════════════════════════════════════════════════════════════
# TABLE 1A — 5-min CCF  (co-active bars only, both% >= 25% fights)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("TABLE 1A — 5-min CCF (co-active bars, fights with both%>=25%)")
print("=" * 70)

rho_list_5, n_list_5 = [], []

for fid in sorted(hi_cov):
    sub = df[(df["fight_id"] == fid) & df["both_traded"]].sort_values("bar_utc")
    if len(sub) < 20:
        continue
    dk  = sub.set_index("bar_utc")["k_last"].diff()
    dpm = sub.set_index("bar_utc")["pm_last"].diff()
    rho, ns = ccf_one_fight(dk, dpm)
    rho_list_5.append(rho)
    n_list_5.append(ns)

rho_avg_5, ci_lo_5, ci_hi_5, rho_mat_5 = fisher_avg_ci(rho_list_5, n_list_5)
lags = list(range(-MAX_LAG, MAX_LAG + 1))

header = f"{'lag':>5}  {'rho_avg':>8}  {'ci_lo':>7}  {'ci_hi':>7}  {'sig?':>5}  {'lead':>12}"
print(f"\n  Convention: corr(dK_t, dPM_{{t+k}})")
print(f"  k>0 => Kalshi leads | k<0 => PM leads | k=0 => contemporaneous")
print(f"  N fights contributing: {len(rho_list_5)}")
print()
print("  " + header)
print("  " + "-" * len(header))
for i, k in enumerate(lags):
    r  = rho_avg_5[i]
    lo = ci_lo_5[i]
    hi = ci_hi_5[i]
    sig = "*" if (lo > 0 or hi < 0) else ""
    if k > 0:  lead = "Kalshi leads"
    elif k < 0: lead = "PM leads"
    else:       lead = "contemporaneous"
    print(f"  {k:>5}  {r:>8.4f}  {lo:>7.4f}  {hi:>7.4f}  {sig:>5}  {lead:>12}")

print()

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 1B — 15-min CCF  (all 20 fights, aggregate 3×5min)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("TABLE 1B — 15-min CCF (all 20 fights, 3x5min aggregation)")
print("=" * 70)

def aggregate_to_15min(sub: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate 5-min bars to 15-min bars.
    last = last non-NaN last_price in the 15-min window.
    n = sum of trades in the 15-min window.
    Only include 15-min bars where both venues have >= 1 trade.
    """
    s = sub.set_index("bar_utc").sort_index()
    # resample to 15-min
    k_last15  = s["k_last"].resample("15min").last()
    pm_last15 = s["pm_last"].resample("15min").last()
    k_n15     = s["k_n"].resample("15min").sum()
    pm_n15    = s["pm_n"].resample("15min").sum()
    out = pd.DataFrame({
        "k_last": k_last15,
        "pm_last": pm_last15,
        "k_n": k_n15,
        "pm_n": pm_n15,
    })
    out["both_traded"] = (out["k_n"] > 0) & (out["pm_n"] > 0)
    return out.reset_index()

rho_list_15, n_list_15 = [], []

for fid in sorted(df["fight_id"].unique()):
    sub = df[df["fight_id"] == fid].sort_values("bar_utc")
    agg = aggregate_to_15min(sub)
    # use co-active bars only for consistency
    agg_co = agg[agg["both_traded"]]
    if len(agg_co) < 10:
        continue
    dk15  = agg_co.set_index("bar_utc")["k_last"].diff()
    dpm15 = agg_co.set_index("bar_utc")["pm_last"].diff()
    rho, ns = ccf_one_fight(dk15, dpm15)
    rho_list_15.append(rho)
    n_list_15.append(ns)

rho_avg_15, ci_lo_15, ci_hi_15, rho_mat_15 = fisher_avg_ci(rho_list_15, n_list_15)

print(f"\n  Convention: corr(dK_t, dPM_{{t+k}})")
print(f"  k>0 => Kalshi leads | k<0 => PM leads | k=0 => contemporaneous")
print(f"  N fights contributing: {len(rho_list_15)}")
print()
print("  " + header)
print("  " + "-" * len(header))
for i, k in enumerate(lags):
    r  = rho_avg_15[i]
    lo = ci_lo_15[i]
    hi = ci_hi_15[i]
    sig = "*" if (lo > 0 or hi < 0) else ""
    if k > 0:  lead = "Kalshi leads"
    elif k < 0: lead = "PM leads"
    else:       lead = "contemporaneous"
    print(f"  {k:>5}  {r:>8.4f}  {lo:>7.4f}  {hi:>7.4f}  {sig:>5}  {lead:>12}")

print()

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 2 — JUMP RESPONSE
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("TABLE 2 — Jump response (|ret| >= 3 cents on venue A)")
print("=" * 70)

JUMP_THRESH = 0.03   # 3 cents
HORIZON_30  = 6      # 6 × 5-min = 30 min
HORIZON_60  = 12     # 12 × 5-min = 60 min

def jump_response_analysis(panel: pd.DataFrame, venue_a: str, venue_b: str,
                            thresh: float, h30: int, h60: int):
    """
    For each jump on venue_a (|ret_a| >= thresh), measure venue_b's
    cumulative return over the next h30 and h60 bars, signed by jump direction.
    Returns dict with stats.
    """
    col_a = f"{venue_a}_last"
    col_b = f"{venue_b}_last"

    results_30, results_60 = [], []
    n_jumps = 0

    for fid in panel["fight_id"].unique():
        sub = (
            panel[panel["fight_id"] == fid]
            .sort_values("bar_utc")
            .reset_index(drop=True)
        )
        ret_a = sub[col_a].diff()
        ret_b = sub[col_b].diff()

        for i in range(1, len(sub) - h60):
            ra = ret_a.iloc[i]
            if not np.isfinite(ra) or abs(ra) < thresh:
                continue
            sign = np.sign(ra)

            # cumulative return on B over next h30 bars (signed by jump direction)
            fwd_30 = ret_b.iloc[i + 1: i + 1 + h30]
            fwd_60 = ret_b.iloc[i + 1: i + 1 + h60]

            # require at least half the bars to be finite
            if fwd_30.notna().sum() >= h30 // 2:
                results_30.append(sign * fwd_30.sum())
                n_jumps += 1  # count once
            if fwd_60.notna().sum() >= h60 // 2:
                results_60.append(sign * fwd_60.sum())

    if not results_30:
        return {"n_jumps": 0}

    r30 = np.array(results_30)
    r60 = np.array(results_60) if results_60 else np.array([np.nan])

    return {
        "n_jumps":       len(r30),
        "mean_30":       np.nanmean(r30),
        "same_dir_30":   np.mean(r30 > 0),
        "mean_60":       np.nanmean(r60),
        "same_dir_60":   np.mean(r60 > 0),
    }


# unconditional mean return for baseline
def unconditional_mean(panel, col):
    ret = panel.groupby("fight_id")[col].diff()
    return ret.dropna().mean(), ret.dropna().std()

k_mu, k_std   = unconditional_mean(df, "k_last")
pm_mu, pm_std = unconditional_mean(df, "pm_last")

print(f"\n  Unconditional mean 5-min return:  Kalshi={k_mu:.5f}  PM={pm_mu:.5f}")
print(f"  Jump threshold: |ret| >= {JUMP_THRESH:.2f}\n")

for direction, a, b, b_mu in [
    ("K-jumps -> PM response", "k", "pm", pm_mu),
    ("PM-jumps -> K response", "pm", "k", k_mu),
]:
    stats = jump_response_analysis(df, a, b, JUMP_THRESH, HORIZON_30, HORIZON_60)
    if stats["n_jumps"] == 0:
        print(f"  {direction}: no jumps found")
        continue

    print(f"  {direction}")
    print(f"    N jumps:                {stats['n_jumps']}")
    print(f"    30-min cumul response:  {stats['mean_30']:+.5f}  (baseline B_mu*6={b_mu*HORIZON_30:+.5f})  same_dir={stats['same_dir_30']:.1%}")
    print(f"    60-min cumul response:  {stats['mean_60']:+.5f}  (baseline B_mu*12={b_mu*HORIZON_60:+.5f})  same_dir={stats['same_dir_60']:.1%}")
    print()

# ══════════════════════════════════════════════════════════════════════════════
# WRITE QA/MARKDOWN
# ══════════════════════════════════════════════════════════════════════════════
def fmt_row(k, r, lo, hi, sig):
    lead = "Kalshi leads" if k > 0 else ("PM leads" if k < 0 else "contemporaneous")
    s = "*" if sig else ""
    return f"| {k:+d} | {r:+.4f} | {lo:+.4f} | {hi:+.4f} | {s} | {lead} |"

j_stats = {}
for a_lbl, b_lbl, b_mu_val in [("k","pm",pm_mu),("pm","k",k_mu)]:
    j_stats[(a_lbl, b_lbl)] = jump_response_analysis(
        df, a_lbl, b_lbl, JUMP_THRESH, HORIZON_30, HORIZON_60
    )
    j_stats[(a_lbl, b_lbl)]["b_mu"] = b_mu_val

# verdicts
def verdict_lead(rho_avg, ci_lo, ci_hi, lags):
    lags_arr = np.array(lags)
    # Kalshi leads: check k=+1,+2 (positive k, corr positive and CI > 0)
    k_lead_sigs = [
        i for i, k in enumerate(lags_arr)
        if k > 0 and ci_lo[i] > 0
    ]
    pm_lead_sigs = [
        i for i, k in enumerate(lags_arr)
        if k < 0 and ci_hi[i] < 0
    ]
    return k_lead_sigs, pm_lead_sigs

kl5, pl5 = verdict_lead(rho_avg_5, ci_lo_5, ci_hi_5, lags)
kl15, pl15 = verdict_lead(rho_avg_15, ci_lo_15, ci_hi_15, lags)

def verdict_str(kl, pl, strat):
    lags_arr = np.array(lags)
    if kl and pl:
        k_lags = [lags[i] for i in kl]
        p_lags = [lags[i] for i in pl]
        return f"Both venues show lead-lag evidence at {strat}: Kalshi at k={k_lags}, PM at k={p_lags}."
    elif kl:
        k_lags = [lags[i] for i in kl]
        return f"Kalshi leads PM at {strat}: significant positive CCF at k={k_lags}."
    elif pl:
        p_lags = [lags[i] for i in pl]
        return f"PM leads Kalshi at {strat}: significant negative CCF at k={p_lags}."
    else:
        return f"No significant lead-lag detected at {strat} (bootstrap CI spans zero at all non-zero lags)."

v1 = verdict_str(kl5, pl5, "5-min")
v2 = verdict_str(kl15, pl15, "15-min")

# jump verdict
jkp = j_stats[("k","pm")]
jpk = j_stats[("pm","k")]
jump_v_parts = []
if jkp["n_jumps"] > 0:
    excess = jkp["mean_30"] - jkp["b_mu"] * HORIZON_30
    if jkp["same_dir_30"] > 0.6 or abs(excess) > 0.005:
        jump_v_parts.append(f"K-jumps propagate to PM (same-dir={jkp['same_dir_30']:.0%} at 30 min, excess={excess:+.4f})")
    else:
        jump_v_parts.append(f"K-jumps do NOT clearly propagate to PM (same-dir={jkp['same_dir_30']:.0%} at 30 min)")
if jpk["n_jumps"] > 0:
    excess = jpk["mean_30"] - jpk["b_mu"] * HORIZON_30
    if jpk["same_dir_30"] > 0.6 or abs(excess) > 0.005:
        jump_v_parts.append(f"PM-jumps propagate to K (same-dir={jpk['same_dir_30']:.0%} at 30 min, excess={excess:+.4f})")
    else:
        jump_v_parts.append(f"PM-jumps do NOT clearly propagate to K (same-dir={jpk['same_dir_30']:.0%} at 30 min)")
v3 = "; ".join(jump_v_parts) if jump_v_parts else "Insufficient jump data."

md = f"""# Phase 2 Prototype — Lead-Lag Analysis
**Generated:** {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
**Panel:** `data/clean/phase2_prototype_panel.parquet` — 20 fights, 16,739 5-min bars

---

## Convention
`corr(dK_t, dPM_{{t+k}})` where `dK_t` = 5-min return on Kalshi, `dPM_{{t+k}}` = PM return k bars later.

- **k > 0** → Kalshi leads (K moves now, PM moves later)
- **k < 0** → PM leads (PM moves earlier, K adjusts later)
- **k = 0** → contemporaneous
- CI = 95% stationary bootstrap across fights (block_len=5, B=1000)
- `*` = CI excludes zero

---

## Table 1A — 5-min CCF (co-active bars, fights with both% ≥ 25%)
Fights: {len(rho_list_5)} / 20 meet threshold

| lag | rho_avg | ci_lo | ci_hi | sig | lead |
|----:|--------:|------:|------:|:---:|:-----|
"""
for i, k in enumerate(lags):
    sig = (ci_lo_5[i] > 0 or ci_hi_5[i] < 0)
    md += fmt_row(k, rho_avg_5[i], ci_lo_5[i], ci_hi_5[i], sig) + "\n"

md += f"""
---

## Table 1B — 15-min CCF (co-active 15-min bars, all 20 fights)
Fights contributing: {len(rho_list_15)} / 20

| lag | rho_avg | ci_lo | ci_hi | sig | lead |
|----:|--------:|------:|------:|:---:|:-----|
"""
for i, k in enumerate(lags):
    sig = (ci_lo_15[i] > 0 or ci_hi_15[i] < 0)
    md += fmt_row(k, rho_avg_15[i], ci_lo_15[i], ci_hi_15[i], sig) + "\n"

md += f"""
---

## Table 2 — Jump Response (|ret| ≥ {JUMP_THRESH:.2f} on venue A, 5-min bars)
Unconditional 5-min mean returns: Kalshi = {k_mu:+.5f}, PM = {pm_mu:+.5f}

### K-jumps → PM response
"""
s = jkp
md += f"""| Metric | 30 min | 60 min |
|:-------|-------:|-------:|
| N jumps | {s['n_jumps']} | {s['n_jumps']} |
| Mean signed cumul return on PM | {s['mean_30']:+.5f} | {s['mean_60']:+.5f} |
| Baseline (PM_mu × h) | {s['b_mu']*HORIZON_30:+.5f} | {s['b_mu']*HORIZON_60:+.5f} |
| Excess return (mean - baseline) | {s['mean_30'] - s['b_mu']*HORIZON_30:+.5f} | {s['mean_60'] - s['b_mu']*HORIZON_60:+.5f} |
| Share PM moves same direction | {s['same_dir_30']:.1%} | {s['same_dir_60']:.1%} |

### PM-jumps → K response
"""
s = jpk
md += f"""| Metric | 30 min | 60 min |
|:-------|-------:|-------:|
| N jumps | {s['n_jumps']} | {s['n_jumps']} |
| Mean signed cumul return on K | {s['mean_30']:+.5f} | {s['mean_60']:+.5f} |
| Baseline (K_mu × h) | {s['b_mu']*HORIZON_30:+.5f} | {s['b_mu']*HORIZON_60:+.5f} |
| Excess return (mean - baseline) | {s['mean_30'] - s['b_mu']*HORIZON_30:+.5f} | {s['mean_60'] - s['b_mu']*HORIZON_60:+.5f} |
| Share K moves same direction | {s['same_dir_30']:.1%} | {s['same_dir_60']:.1%} |

---

## Verdicts

1. **5-min lead-lag:** {v1}
2. **15-min lead-lag:** {v2}
3. **Jump propagation:** {v3}
"""

QA.write_text(md, encoding="utf-8")
print(f"\nQA report written: {QA}")
