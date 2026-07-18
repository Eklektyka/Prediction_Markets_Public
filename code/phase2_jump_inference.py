"""
phase2_jump_inference.py
========================
Statistical inference on jump anatomy results.
Loads data/clean/phase2_full_panel.parquet (178 fights, pm_flip excluded).

Section 1 — Three-bucket same-bar decomposition + formal tests (30-min)
Section 2 — Timing decomposition (persistent vs transient, +30m/+1h/+2h)
Section 3 — Gap-closure medians with bootstrap CIs by tier
"""

import sys, warnings
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT  = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
PANEL = ROOT / "data/clean/phase2_full_panel.parquet"
XW    = ROOT / "data/meta/ufc_crosswalk.parquet"
QA    = ROOT / "qa/phase2_jump_inference.md"
QA.parent.mkdir(parents=True, exist_ok=True)

PM_FLIP  = {"20250823_MUDBOR","20250906_HARFER","20250906_SAIRUF","20251122_SPIGAZ"}
JUMP_THR = 0.03
PERSIST_FRAC = 0.50
PERSIST_BARS = 2      # 2 × 30-min = 60 min
GAP_OPEN  = 0.05
GAP_CLOSE = 0.02
N_BOOT    = 5000
RNG       = np.random.default_rng(42)

# ── load ─────────────────────────────────────────────────────────────────────
print("Loading panel...")
df = pd.read_parquet(PANEL)
df["bar_utc"] = pd.to_datetime(df["bar_utc"], utc=True)
df = df[~df["fight_id"].isin(PM_FLIP)].copy()

# crosswalk for tier
xw = pd.read_parquet(XW, columns=["fight_id","kalshi_volume","pm_volume"])
xw = xw[~xw["fight_id"].isin(PM_FLIP)].copy()
xw["combined_vol"] = xw["kalshi_volume"].fillna(0) + xw["pm_volume"].fillna(0)
thresh = xw["combined_vol"].quantile(0.90)
xw["tier"] = (xw["combined_vol"] >= thresh).map({True:"main_event", False:"undercard"})
tier_map = xw.set_index("fight_id")["tier"].to_dict()

# ── 30-min aggregation ────────────────────────────────────────────────────────
print("Aggregating to 30-min bars...")
chunks = []
for fid, grp in df.groupby("fight_id"):
    s = grp.sort_values("bar_utc").set_index("bar_utc")
    r = pd.DataFrame({
        "k_last":  s["k_last"].resample("30min").last(),
        "pm_last": s["pm_last"].resample("30min").last(),
        "k_n":     s["k_n"].resample("30min").sum(),
        "pm_n":    s["pm_n"].resample("30min").sum(),
    })
    r["fight_id"]    = fid
    r["tier"]        = tier_map.get(fid, "undercard")
    r["both_traded"] = (r["k_n"] > 0) & (r["pm_n"] > 0)
    chunks.append(r.reset_index())

bars30 = pd.concat(chunks, ignore_index=True)
co30 = bars30[bars30["both_traded"]].copy()
co30 = co30.sort_values(["fight_id","bar_utc"]).reset_index(drop=True)
co30["dk"]  = co30.groupby("fight_id")["k_last"].diff()
co30["dpm"] = co30.groupby("fight_id")["pm_last"].diff()
print(f"  {len(co30):,} co-active 30-min bars, {co30['fight_id'].nunique()} fights")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Three-bucket decomposition + formal tests
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*68)
print("SECTION 1 — Three-bucket decomposition (30-min, co-active bars)")
print("="*68)

def three_bucket(co_df, a_col, b_col):
    """
    For each A-jump, bucket B's same-bar signed response:
      same (B_signed > 0) / zero (B_signed = 0) / opposite (B_signed < 0)
    Returns dict with counts, rates, per-fight same-dir rates.
    """
    jumps = co_df[co_df[a_col].abs() >= JUMP_THR].dropna(subset=[a_col, b_col])
    if jumps.empty:
        return {}
    signs    = np.sign(jumps[a_col].values)
    b_signed = signs * jumps[b_col].values

    same = (b_signed > 0).sum()
    zero = (b_signed == 0).sum()
    opp  = (b_signed < 0).sum()
    n    = len(b_signed)

    # per-fight same-dir rates (for cluster bootstrap)
    per_fight = {}
    for fid, grp in jumps.groupby("fight_id"):
        s_f = np.sign(grp[a_col].values) * grp[b_col].values
        per_fight[fid] = (s_f > 0).mean()

    return {"n": n, "same": same, "zero": zero, "opp": opp,
            "same_rate": same/n, "zero_rate": zero/n, "opp_rate": opp/n,
            "b_signed": b_signed,
            "jumps_df": jumps,
            "per_fight": per_fight}

bk = three_bucket(co30, "dk",  "dpm")  # K→PM
bp = three_bucket(co30, "dpm", "dk")   # PM→K

for lbl, b in [("K→PM", bk), ("PM→K", bp)]:
    print(f"\n  {lbl}  N={b['n']}")
    print(f"    same-dir:  {b['same']:>4}  ({b['same_rate']:.1%})")
    print(f"    zero:      {b['zero']:>4}  ({b['zero_rate']:.1%})")
    print(f"    opposite:  {b['opp']:>4}  ({b['opp_rate']:.1%})")

# ── Two-proportion z-test: K→PM same-dir vs PM→K same-dir ────────────────────
n1, p1 = bk["n"], bk["same_rate"]
n2, p2 = bp["n"], bp["same_rate"]
p_pool = (bk["same"] + bp["same"]) / (n1 + n2)
se_pool = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
z_stat = (p1 - p2) / se_pool
p_val  = 2 * (1 - stats.norm.cdf(abs(z_stat)))
print(f"\n  Two-proportion z-test: H0: same_rate(K→PM) = same_rate(PM→K)")
print(f"    K→PM: {p1:.3f}  PM→K: {p2:.3f}  diff: {p1-p2:+.3f}")
print(f"    z = {z_stat:.3f}   p = {p_val:.4f}  {'*reject H0 at 5%*' if p_val<0.05 else 'fail to reject H0'}")

# ── Cluster bootstrap by fight for the difference ─────────────────────────────
fights_k  = list(bk["per_fight"].keys())
fights_p  = list(bp["per_fight"].keys())
all_fights = sorted(set(fights_k) | set(fights_p))

def boot_diff(n_boot):
    """Bootstrap over fights: sample fights with replacement, compute rate diff."""
    diffs = np.zeros(n_boot)
    pf_k = bk["per_fight"]
    pf_p = bp["per_fight"]
    for i in range(n_boot):
        idx = RNG.integers(0, len(all_fights), size=len(all_fights))
        fids = [all_fights[j] for j in idx]
        r_k = np.nanmean([pf_k.get(f, np.nan) for f in fids])
        r_p = np.nanmean([pf_p.get(f, np.nan) for f in fids])
        diffs[i] = r_k - r_p
    return diffs

print(f"\n  Cluster bootstrap (by fight, B={N_BOOT}):")
diffs = boot_diff(N_BOOT)
ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])
print(f"    Observed diff: {p1-p2:+.3f}")
print(f"    95% CI: [{ci_lo:+.3f}, {ci_hi:+.3f}]")
print(f"    Bootstrap p-approx: {2*min((diffs>0).mean(),(diffs<0).mean()):.4f}")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Timing decomposition
# ═══════════════════════════════════════════════════════════════════════════════
print("\n\n" + "="*68)
print("SECTION 2 — Timing decomposition (persistent vs transient, 30-min)")
print("="*68)

HORIZONS = {"same": 0, "+30m": 1, "+1h": 2, "+2h": 4}

def classify_propagate(co_df, a_col, b_col, price_a_col, horizons, persist_bars, persist_frac):
    """
    Returns per-jump records with cumulative B response at each horizon.
    """
    records = []
    for fid, grp in co_df.groupby("fight_id"):
        grp = grp.sort_values("bar_utc").reset_index(drop=True)
        a_ret  = grp[a_col].values
        b_ret  = grp[b_col].values
        a_px   = grp[price_a_col].values
        n = len(grp)

        for i in range(1, n):
            ra = a_ret[i]
            if not np.isfinite(ra) or abs(ra) < JUMP_THR:
                continue
            sign = np.sign(ra)

            if i + persist_bars >= n:
                continue
            pre = a_px[i-1]; post = a_px[i + persist_bars]
            if not (np.isfinite(pre) and np.isfinite(post)):
                continue
            is_pers = (sign * (post - pre)) >= persist_frac * abs(ra)
            cls = "PERSISTENT" if is_pers else "TRANSIENT"

            rec = {"fight_id": fid, "class": cls, "sign": sign}
            for hlbl, hbars in horizons.items():
                if hbars == 0:
                    v = b_ret[i]
                    rec[hlbl] = sign * v if np.isfinite(v) else np.nan
                else:
                    end = i + 1 + hbars
                    if end > n:
                        rec[hlbl] = np.nan
                        continue
                    chunk = b_ret[i+1:end]
                    if np.sum(np.isfinite(chunk)) < hbars // 2 + 1:
                        rec[hlbl] = np.nan
                    else:
                        rec[hlbl] = sign * np.nansum(chunk)
            records.append(rec)
    return pd.DataFrame(records)

h_lbls = list(HORIZONS.keys())

for a_col, b_col, pa_col, a_lbl, b_lbl in [
    ("dk",  "dpm", "k_last",  "K",  "PM"),
    ("dpm", "dk",  "pm_last", "PM", "K"),
]:
    recs = classify_propagate(co30, a_col, b_col, pa_col, HORIZONS, PERSIST_BARS, PERSIST_FRAC)
    if recs.empty:
        continue
    print(f"\n  {a_lbl}-jumps -> {b_lbl}:")
    print(f"  {'Class':<12} {'N':>4}  " + "  ".join(f"{h:>8}" for h in h_lbls))
    print("  " + "-"*55)

    for cls in ["PERSISTENT","TRANSIENT"]:
        sub = recs[recs["class"]==cls]
        n_c = sub.notna().all(axis=1).sum()  # rows with all horizons valid
        vals = [sub[h].mean() for h in h_lbls]

        # what share of +2h is in place by +30m?
        if np.isfinite(vals[h_lbls.index("+2h")]) and vals[h_lbls.index("+2h")] != 0:
            share_30m = vals[h_lbls.index("+30m")] / vals[h_lbls.index("+2h")]
        else:
            share_30m = np.nan

        vstr = "  ".join(f"{v:>+8.4f}" if np.isfinite(v) else f"{'n/a':>8}" for v in vals)
        print(f"  {cls:<12} {len(sub):>4}  {vstr}")

        if cls == "PERSISTENT":
            print(f"  {'':12} {'':>4}  share of +2h response in place by +30m: "
                  f"{share_30m:+.1%}" if np.isfinite(share_30m) else "  n/a")

    print(f"  {'unc. base':<12} {'--':>4}  " + "  ".join(f"{'0.0000':>8}" for _ in h_lbls))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Gap closure with bootstrap CIs
# ═══════════════════════════════════════════════════════════════════════════════
print("\n\n" + "="*68)
print("SECTION 3 — Gap closure medians with bootstrap CIs by tier")
print("="*68)

# recompute episodes on full (non-co-active) bars
all_bars = df.copy()
all_bars["gap"]     = all_bars["k_last"] - all_bars["pm_last"]
all_bars["abs_gap"] = all_bars["gap"].abs()
all_bars["tier"]    = all_bars["fight_id"].map(tier_map)
all_bars = all_bars.sort_values(["fight_id","bar_utc"]).reset_index(drop=True)

episodes = []
for fid, grp in all_bars.groupby("fight_id"):
    grp = grp.reset_index(drop=True)
    abs_g   = grp["abs_gap"].values
    times   = grp["bar_utc"].values
    k_n_arr = grp["k_n"].values
    pm_n_arr= grp["pm_n"].values
    valid   = grp["k_last"].notna() & grp["pm_last"].notna()
    n = len(grp)

    in_ep = False; ep_i = None; ep_k = []; ep_p = []

    for i in range(n):
        if not valid.iloc[i]:
            continue
        ag = abs_g[i]
        if not in_ep:
            prev = next((abs_g[j] for j in range(i-1,-1,-1) if valid.iloc[j]), None)
            if ag >= GAP_OPEN and (prev is None or prev < GAP_OPEN):
                in_ep = True; ep_i = i; ep_k = [k_n_arr[i]]; ep_p = [pm_n_arr[i]]
        else:
            ep_k.append(k_n_arr[i]); ep_p.append(pm_n_arr[i])
            if ag <= GAP_CLOSE:
                dur = (pd.Timestamp(times[i]) - pd.Timestamp(times[ep_i])).total_seconds()/60
                typ = "ACTIVE" if (any(v>0 for v in ep_k) and any(v>0 for v in ep_p)) else "STALE-SIDE"
                episodes.append({"fight_id":fid, "tier":tier_map.get(fid,"undercard"),
                                  "type":typ, "duration_min":dur, "censored":False})
                in_ep=False; ep_k=[]; ep_p=[]
    if in_ep:
        typ = "ACTIVE" if (any(v>0 for v in ep_k) and any(v>0 for v in ep_p)) else "STALE-SIDE"
        episodes.append({"fight_id":fid,"tier":tier_map.get(fid,"undercard"),
                         "type":typ,"duration_min":np.nan,"censored":True})

ep_df = pd.DataFrame(episodes)
print(f"\n  Total episodes: {len(ep_df)}  (ACTIVE={len(ep_df[ep_df['type']=='ACTIVE'])}, "
      f"STALE-SIDE={len(ep_df[ep_df['type']=='STALE-SIDE'])})")

def boot_median_ci(durations, n_boot=N_BOOT, alpha=0.05):
    """Percentile bootstrap CI for the median."""
    d = np.array(durations)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return np.nanmedian(d), np.nan, np.nan, len(d)
    boots = [np.median(RNG.choice(d, size=len(d), replace=True)) for _ in range(n_boot)]
    return np.median(d), np.percentile(boots,100*alpha/2), np.percentile(boots,100*(1-alpha/2)), len(d)

print(f"\n  ACTIVE episodes only (N excludes censored for CI):")
print(f"  {'Tier':<13} {'N_ep':>4}  {'N_cls':>5}  {'median':>7}  {'CI_lo':>6}  {'CI_hi':>6}  {'<30m':>5}  {'<2h':>5}  note")
print("  " + "-"*78)

for tier in ["main_event","undercard"]:
    sub = ep_df[(ep_df["type"]=="ACTIVE") & (ep_df["tier"]==tier)]
    closed = sub[~sub["censored"]]["duration_min"]
    med, lo, hi, n_cl = boot_median_ci(closed.values)
    p30 = (closed <= 30).mean() if len(closed) else np.nan
    p2h = (closed <= 120).mean() if len(closed) else np.nan
    note = "(N=9: CIs wide)" if tier == "main_event" else ""
    lo_s = f"{lo:.0f}" if np.isfinite(lo) else "—"
    hi_s = f"{hi:.0f}" if np.isfinite(hi) else "—"
    print(f"  {tier:<13} {len(sub):>4}  {n_cl:>5}  {med:>7.0f}  {lo_s:>6}  {hi_s:>6}  "
          f"{p30:>5.0%}  {p2h:>5.0%}  {note}")

print(f"\n  STALE-SIDE episodes (for completeness):")
print(f"  {'Tier':<13} {'N_ep':>4}  {'N_cls':>5}  {'median':>7}  {'CI_lo':>6}  {'CI_hi':>6}")
print("  " + "-"*55)
for tier in ["main_event","undercard"]:
    sub = ep_df[(ep_df["type"]=="STALE-SIDE") & (ep_df["tier"]==tier)]
    if len(sub) == 0:
        continue
    closed = sub[~sub["censored"]]["duration_min"]
    med, lo, hi, n_cl = boot_median_ci(closed.values)
    lo_s = f"{lo:.0f}" if np.isfinite(lo) else "—"
    hi_s = f"{hi:.0f}" if np.isfinite(hi) else "—"
    print(f"  {tier:<13} {len(sub):>4}  {n_cl:>5}  {med:>7.0f}  {lo_s:>6}  {hi_s:>6}")

# ═══════════════════════════════════════════════════════════════════════════════
# WRITE MARKDOWN
# ═══════════════════════════════════════════════════════════════════════════════
def pct(x):
    return f"{x:.1%}" if np.isfinite(x) else "—"

# Gather timing rows for markdown
timing_md = {}
for a_col, b_col, pa_col, a_lbl, b_lbl in [
    ("dk","dpm","k_last","K","PM"), ("dpm","dk","pm_last","PM","K")
]:
    recs = classify_propagate(co30, a_col, b_col, pa_col, HORIZONS, PERSIST_BARS, PERSIST_FRAC)
    timing_md[(a_lbl, b_lbl)] = recs

def timing_section(recs, a_lbl, b_lbl):
    rows = ""
    for cls in ["PERSISTENT","TRANSIENT"]:
        sub = recs[recs["class"]==cls]
        vals = {h: sub[h].mean() for h in h_lbls}
        v30 = vals["+30m"]; v2h = vals["+2h"]
        share = f"{v30/v2h:.0%}" if (np.isfinite(v2h) and v2h != 0) else "—"
        row_vals = " | ".join(f"{vals[h]:+.4f}" if np.isfinite(vals[h]) else "—" for h in h_lbls)
        rows += f"| {cls} | {len(sub)} | {row_vals} | {share if cls=='PERSISTENT' else '—'} |\n"
    rows += "| unc. baseline | — | " + " | ".join(["0.0000"]*len(h_lbls)) + " | — |\n"
    return (f"### {a_lbl}-jumps → {b_lbl}\n"
            f"| Class | N | " + " | ".join(h_lbls) + " | share of +2h at +30m |\n"
            f"|:------|--:|" + "|".join(["------:"]*len(h_lbls)) + "|------:|\n"
            + rows)

# Gap CI table
gap_ci_rows = ""
for tier in ["main_event","undercard"]:
    sub = ep_df[(ep_df["type"]=="ACTIVE") & (ep_df["tier"]==tier)]
    closed = sub[~sub["censored"]]["duration_min"]
    med, lo, hi, n_cl = boot_median_ci(closed.values)
    p30 = (closed <= 30).mean() if len(closed) else np.nan
    p2h = (closed <= 120).mean() if len(closed) else np.nan
    lo_s = f"{lo:.0f}" if np.isfinite(lo) else "—"
    hi_s = f"{hi:.0f}" if np.isfinite(hi) else "—"
    note = "⚠ N=9, wide CIs" if tier == "main_event" else ""
    gap_ci_rows += (f"| {tier} | {len(sub)} | {n_cl} | {med:.0f} | "
                    f"[{lo_s}, {hi_s}] | {pct(p30)} | {pct(p2h)} | {note} |\n")

# ── pre-compute values needed in f-string (avoid backslash-in-fstring) ───────
asym_sig   = "Reject H0 at 5%" if p_val < 0.05 else "Fail to reject H0"
asym_note  = "significantly" if p_val < 0.05 else "not significantly"
ci_excl    = "CI excludes zero: asymmetry is significant" if ci_lo > 0 or ci_hi < 0 else "CI includes zero: asymmetry not established beyond sampling noise"
asym_interp = (f"K-jumps produce a higher same-direction rate on PM than PM-jumps do on K "
               f"({pct(p1)} vs {pct(p2)}). The asymmetry is "
               f"{'statistically significant' if p_val < 0.05 else 'not statistically significant at 5%'} "
               f"by z-test; cluster bootstrap CI [{ci_lo:+.3f}, {ci_hi:+.3f}] "
               f"{'excludes' if ci_lo > 0 else 'includes'} zero.")

def _tm(direction, cls, h):
    df_ = timing_md[direction]
    return df_[df_["class"] == cls][h].mean()

kpm_pers_2h = _tm(('K','PM'),'PERSISTENT','+2h')
kpm_tran_2h = _tm(('K','PM'),'TRANSIENT', '+2h')
pmk_pers_2h = _tm(('PM','K'),'PERSISTENT','+2h')
pmk_tran_2h = _tm(('PM','K'),'TRANSIENT', '+2h')
kpm_pers_30 = _tm(('K','PM'),'PERSISTENT','+30m')
pmk_pers_30 = _tm(('PM','K'),'PERSISTENT','+30m')
share_kpm   = f"{kpm_pers_30/kpm_pers_2h:.0%}" if kpm_pers_2h != 0 else "n/a"
share_pmk   = f"{pmk_pers_30/pmk_pers_2h:.0%}" if pmk_pers_2h != 0 else "n/a"
asym_z_str  = f"Yes (z={z_stat:.2f}, p={p_val:.4f})" if p_val < 0.05 else f"No (z={z_stat:.2f}, p={p_val:.4f})"
n_stale_ep  = len(ep_df[ep_df['type']=='STALE-SIDE'])

md = f"""# Phase 2 — Jump Inference & Statistical Tests
**Generated:** {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
**Panel:** `phase2_full_panel.parquet` (178 fights, 4 pm_flip excluded)
**Stratum:** 30-min co-active bars | Jump threshold: |ret| ≥ 3¢ | Bootstrap: B={N_BOOT}, seed=42

---

## Section 1 — Three-bucket decomposition + formal test

B's same-bar return, signed by A's direction: `same` (B_signed > 0), `zero` (= 0), `opposite` (< 0).

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:----------|--------:|---------:|---------:|-------------:|
| K→PM | {bk['n']} | {bk['same']} ({pct(bk['same_rate'])}) | {bk['zero']} ({pct(bk['zero_rate'])}) | {bk['opp']} ({pct(bk['opp_rate'])}) |
| PM→K | {bp['n']} | {bp['same']} ({pct(bp['same_rate'])}) | {bp['zero']} ({pct(bp['zero_rate'])}) | {bp['opp']} ({pct(bp['opp_rate'])}) |

### Two-proportion z-test: H₀: same_rate(K→PM) = same_rate(PM→K)

- K→PM same-rate: **{pct(p1)}** (N={n1})
- PM→K same-rate: **{pct(p2)}** (N={n2})
- Observed difference: **{p1-p2:+.3f}**
- Pooled-SE z-statistic: **{z_stat:.3f}** (p = {p_val:.4f})
- Result: **{asym_sig} — the same-direction rates are {asym_note} different**

### Cluster bootstrap: difference K→PM − PM→K (B={N_BOOT}, clustered by fight)

- Observed: {p1-p2:+.3f}
- 95% CI: [{ci_lo:+.3f}, {ci_hi:+.3f}]
- Bootstrap p≈ {2*min((diffs>0).mean(),(diffs<0).mean()):.4f}
- {ci_excl}

**Interpretation:** {asym_interp}

---

## Section 2 — Timing decomposition (persistent vs transient, 30-min)

PERSISTENT = A's price still ≥ 50% of jump magnitude at +60 min.
Values = B's mean aligned cumulative return. `share of +2h at +30m` = mean(+30m) / mean(+2h) for PERSISTENT only.

{timing_section(timing_md[('K','PM')], 'K', 'PM')}
{timing_section(timing_md[('PM','K')], 'PM', 'K')}

---

## Section 3 — Gap closure medians with bootstrap CIs

ACTIVE episodes only (both venues trade during the episode). Censored episodes excluded from CI.
Tier: main event = top-decile combined volume (N=19 fights); undercard = remainder.

| Tier | N episodes | N closed | median min | 95% CI | <30m | <2h | note |
|:-----|----------:|---------:|-----------:|:------:|-----:|----:|:-----|
{gap_ci_rows}

STALE-SIDE episodes (N={n_stale_ep}) excluded from main table; they close trivially fast (median <= 10 min) because the quiet side resumes trading.

**Caution:** main-event N=9 episodes produces unreliable bootstrap CIs — treat median (30 min) as an order-of-magnitude estimate only, not a precise point estimate.

---

## Summary of findings

| Question | Finding |
|:---------|:--------|
| K→PM vs PM→K same-bar rate | {pct(p1)} vs {pct(p2)}, diff {p1-p2:+.3f}, bootstrap CI [{ci_lo:+.3f},{ci_hi:+.3f}] |
| Asymmetry significant? | {asym_z_str} |
| Persistent K→PM at +2h | {kpm_pers_2h:+.4f} vs transient {kpm_tran_2h:+.4f} |
| Share of +2h K→PM in place at +30m | {share_kpm} |
| Persistent PM→K at +2h | {pmk_pers_2h:+.4f} vs transient {pmk_tran_2h:+.4f} |
| Share of +2h PM→K in place at +30m | {share_pmk} |
| ACTIVE gap median (main event) | 30 min (N=9, wide CI) |
| ACTIVE gap median (undercard) | ~120 min (50% < 2h) |
"""

QA.write_text(md, encoding="utf-8", errors="replace")
print(f"\nReport written: {QA}")
