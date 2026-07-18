"""
phase2_asymmetry_robustness.py
==============================
Two-stage bootstrap: Stage 1 sweeps fights ONCE and stores per-fight
summary statistics. Stage 2 resamples the summary rows — no recomputation.

Sections:
  1. Speed-asymmetry cluster bootstrap (K->PM vs PM->K, share of +2h at +30m)
  2. Size-conditioned rerun (>= 5 cents)
  3. Summary table
"""

import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

ROOT  = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
PANEL = ROOT / "data/clean/phase2_full_panel.parquet"
XW    = ROOT / "data/meta/ufc_crosswalk.parquet"
QA    = ROOT / "qa/phase2_asymmetry_robustness.md"
QA.parent.mkdir(parents=True, exist_ok=True)

PM_FLIP      = {"20250823_MUDBOR","20250906_HARFER","20250906_SAIRUF","20251122_SPIGAZ"}
THRESHOLDS   = [0.03, 0.05]
PERSIST_FRAC = 0.50
PERSIST_BARS = 2          # 2 x 30-min = 60 min
HORIZONS     = {"same": 0, "+30m": 1, "+1h": 2, "+2h": 4}
H_LBLS       = list(HORIZONS.keys())
N_BOOT       = 500
MIN_N        = 30
RNG          = np.random.default_rng(42)

# ── load & 30-min aggregation ─────────────────────────────────────────────────
t0 = time.time()
print("Loading panel...")
df = pd.read_parquet(PANEL)
df["bar_utc"] = pd.to_datetime(df["bar_utc"], utc=True)
df = df[~df["fight_id"].isin(PM_FLIP)].copy()
print(f"  {df['fight_id'].nunique()} fights, {len(df):,} bars  ({time.time()-t0:.1f}s)")

print("30-min aggregation...")
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
    r["both_traded"] = (r["k_n"] > 0) & (r["pm_n"] > 0)
    chunks.append(r.reset_index())

co30 = pd.concat(chunks, ignore_index=True)
co30 = co30[co30["both_traded"]].sort_values(["fight_id","bar_utc"]).reset_index(drop=True)
co30["dk"]  = co30.groupby("fight_id")["k_last"].diff()
co30["dpm"] = co30.groupby("fight_id")["pm_last"].diff()
all_fights = sorted(co30["fight_id"].unique())
F = len(all_fights)
print(f"  {len(co30):,} co-active 30-min bars, {F} fights  ({time.time()-t0:.1f}s)")

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1: single sweep — compute per-fight summary statistics
# ══════════════════════════════════════════════════════════════════════════════
print(f"\nStage 1: per-fight statistics sweep...")
t1 = time.time()

DIRS    = ["K->PM", "PM->K"]
CLASSES = ["PERSISTENT", "TRANSIENT"]

# Storage: fight_idx x (dir, cls, thr, horizon) -> (sum, count)
# Build lookup: fight_id -> index
fid_idx = {fid: i for i, fid in enumerate(all_fights)}

# For bucket stats (same/zero/opp counts): array [F, n_dirs, n_thrs]
bucket_same  = np.zeros((F, 2, 2), dtype=np.int32)   # [fight, dir, thr]
bucket_zero  = np.zeros((F, 2, 2), dtype=np.int32)
bucket_opp   = np.zeros((F, 2, 2), dtype=np.int32)

# For timing stats: [fight, dir, cls, thr, horizon] -> (sum, count)
n_h = len(H_LBLS)
timing_sum   = np.zeros((F, 2, 2, 2, n_h))  # [fight, dir, cls, thr, horizon]
timing_cnt   = np.zeros((F, 2, 2, 2, n_h), dtype=np.int32)

DIR_IDX = {"K->PM": 0, "PM->K": 1}
THR_IDX = {0.03: 0, 0.05: 1}
CLS_IDX = {"PERSISTENT": 0, "TRANSIENT": 1}

for fid, grp in co30.groupby("fight_id"):
    fi = fid_idx[fid]
    grp  = grp.sort_values("bar_utc").reset_index(drop=True)
    n    = len(grp)
    k_px = grp["k_last"].values
    p_px = grp["pm_last"].values
    dk   = grp["dk"].values
    dpm  = grp["dpm"].values

    for di, (a_ret, b_ret, a_px) in enumerate([
        (dk,  dpm, k_px),
        (dpm, dk,  p_px),
    ]):
        for ti, thr in enumerate(THRESHOLDS):
            for i in range(1, n):
                ra = a_ret[i]
                if not np.isfinite(ra) or abs(ra) < thr:
                    continue
                sign = np.sign(ra)
                rb   = b_ret[i]

                # bucket (only need same-bar rb)
                if np.isfinite(rb):
                    signed = sign * rb
                    if signed > 0:  bucket_same[fi, di, ti] += 1
                    elif signed == 0: bucket_zero[fi, di, ti] += 1
                    else:           bucket_opp[fi, di, ti] += 1

                # timing / persistence classification
                if i + PERSIST_BARS >= n:
                    continue
                pre  = a_px[i - 1]
                post = a_px[i + PERSIST_BARS]
                if not (np.isfinite(pre) and np.isfinite(post)):
                    continue
                is_pers = (sign * (post - pre)) >= PERSIST_FRAC * abs(ra)
                ci = 0 if is_pers else 1   # PERSISTENT=0, TRANSIENT=1

                for hi, (hlbl, hbars) in enumerate(HORIZONS.items()):
                    if hbars == 0:
                        v = rb
                    else:
                        end = i + 1 + hbars
                        if end > n:
                            continue
                        chunk = b_ret[i + 1:end]
                        if np.sum(np.isfinite(chunk)) < hbars // 2 + 1:
                            continue
                        v = np.nansum(chunk)
                    val = sign * v
                    if np.isfinite(val):
                        timing_sum[fi, di, ci, ti, hi] += val
                        timing_cnt[fi, di, ci, ti, hi] += 1

t_stage1 = time.time() - t1
print(f"  Stage 1 complete in {t_stage1:.2f}s")

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2: bootstrap by resampling fight rows — pure numpy
# ══════════════════════════════════════════════════════════════════════════════
print(f"\nStage 2: bootstrap ({N_BOOT} iterations, resampling {F} fight rows)...")
t2 = time.time()

# Bootstrap index matrix: [N_BOOT, F]
boot_idx = RNG.integers(0, F, size=(N_BOOT, F))

def agg_mean(arr_sum, arr_cnt, boot_idx):
    """Vectorised: for each bootstrap sample, weighted mean = sum/count."""
    # arr_sum/cnt: shape [F, ...]
    # boot_idx: [N_BOOT, F]
    # returns: [N_BOOT, ...]
    s = arr_sum[boot_idx].sum(axis=1)   # [N_BOOT, ...]
    c = arr_cnt[boot_idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c > 0, s / c, np.nan)

def boot_ci(boot_vals, obs, alpha=0.05):
    v = boot_vals[np.isfinite(boot_vals)]
    if len(v) < 10:
        return np.nan, np.nan, np.nan
    lo, hi = np.percentile(v, [100*alpha/2, 100*(1-alpha/2)])
    p = 2 * min((v > 0).mean(), (v < 0).mean())
    return lo, hi, p

# ── speed asymmetry bootstrap (3c, persistent) ───────────────────────────────
# speed = mean(+30m) / mean(+2h) per direction at thr=0.03, cls=PERSISTENT
ti3 = 0   # threshold index for 3c
ci_p = 0  # class index PERSISTENT
hi30 = H_LBLS.index("+30m")
hi2h = H_LBLS.index("+2h")

# K->PM speed samples
m30_k = agg_mean(timing_sum[:, 0, ci_p, ti3, hi30],
                 timing_cnt[:, 0, ci_p, ti3, hi30], boot_idx)
m2h_k = agg_mean(timing_sum[:, 0, ci_p, ti3, hi2h],
                 timing_cnt[:, 0, ci_p, ti3, hi2h], boot_idx)
with np.errstate(invalid="ignore", divide="ignore"):
    speed_k_boot = np.where(m2h_k != 0, m30_k / m2h_k, np.nan)

# PM->K speed samples
m30_p = agg_mean(timing_sum[:, 1, ci_p, ti3, hi30],
                 timing_cnt[:, 1, ci_p, ti3, hi30], boot_idx)
m2h_p = agg_mean(timing_sum[:, 1, ci_p, ti3, hi2h],
                 timing_cnt[:, 1, ci_p, ti3, hi2h], boot_idx)
with np.errstate(invalid="ignore", divide="ignore"):
    speed_p_boot = np.where(m2h_p != 0, m30_p / m2h_p, np.nan)

speed_diff_boot = speed_k_boot - speed_p_boot
lo_spd, hi_spd, p_spd = boot_ci(speed_diff_boot, 0)

# observed speed values (using full data)
obs_m30k = timing_sum[:, 0, ci_p, ti3, hi30].sum() / max(timing_cnt[:, 0, ci_p, ti3, hi30].sum(), 1)
obs_m2hk = timing_sum[:, 0, ci_p, ti3, hi2h].sum() / max(timing_cnt[:, 0, ci_p, ti3, hi2h].sum(), 1)
obs_m30p = timing_sum[:, 1, ci_p, ti3, hi30].sum() / max(timing_cnt[:, 1, ci_p, ti3, hi30].sum(), 1)
obs_m2hp = timing_sum[:, 1, ci_p, ti3, hi2h].sum() / max(timing_cnt[:, 1, ci_p, ti3, hi2h].sum(), 1)
obs_spd_k = obs_m30k / obs_m2hk if obs_m2hk != 0 else np.nan
obs_spd_p = obs_m30p / obs_m2hp if obs_m2hp != 0 else np.nan
obs_spd_diff = obs_spd_k - obs_spd_p

# ── same-dir rate bootstrap (both thresholds) ─────────────────────────────────
def boot_sdr_diff(thr_idx):
    same_k = agg_mean(bucket_same[:, 0, thr_idx].astype(float),
                      (bucket_same[:, 0, thr_idx] + bucket_zero[:, 0, thr_idx] +
                       bucket_opp[:, 0, thr_idx]).astype(float), boot_idx)
    same_p = agg_mean(bucket_same[:, 1, thr_idx].astype(float),
                      (bucket_same[:, 1, thr_idx] + bucket_zero[:, 1, thr_idx] +
                       bucket_opp[:, 1, thr_idx]).astype(float), boot_idx)
    return same_k - same_p

sdr_diff_3c = boot_sdr_diff(0)
sdr_diff_5c = boot_sdr_diff(1)
lo_sdr3, hi_sdr3, p_sdr3 = boot_ci(sdr_diff_3c, 0)
lo_sdr5, hi_sdr5, p_sdr5 = boot_ci(sdr_diff_5c, 0)

# ── zero-rate bootstrap (both thresholds) ─────────────────────────────────────
def boot_zero_diff(thr_idx):
    # zero_rate_PM - zero_rate_K
    zero_k = agg_mean(bucket_zero[:, 0, thr_idx].astype(float),
                      (bucket_same[:, 0, thr_idx] + bucket_zero[:, 0, thr_idx] +
                       bucket_opp[:, 0, thr_idx]).astype(float), boot_idx)
    zero_p = agg_mean(bucket_zero[:, 1, thr_idx].astype(float),
                      (bucket_same[:, 1, thr_idx] + bucket_zero[:, 1, thr_idx] +
                       bucket_opp[:, 1, thr_idx]).astype(float), boot_idx)
    return zero_p - zero_k   # PM higher is the asymmetry

zdiff_3c = boot_zero_diff(0)
zdiff_5c = boot_zero_diff(1)
lo_z3, hi_z3, p_z3 = boot_ci(zdiff_3c, 0)
lo_z5, hi_z5, p_z5 = boot_ci(zdiff_5c, 0)

t_stage2 = time.time() - t2
print(f"  Stage 2 complete in {t_stage2:.2f}s")

# ══════════════════════════════════════════════════════════════════════════════
# AGGREGATE OBSERVED STATS (for printing and markdown)
# ══════════════════════════════════════════════════════════════════════════════
def obs_bucket(di, ti):
    sm = bucket_same[:, di, ti].sum()
    zr = bucket_zero[:, di, ti].sum()
    op = bucket_opp[:, di, ti].sum()
    n  = sm + zr + op
    return {"n": n, "same": sm, "zero": zr, "opp": op,
            "same_rate": sm/n if n else np.nan,
            "zero_rate": zr/n if n else np.nan,
            "opp_rate":  op/n if n else np.nan}

def obs_timing(di, ci, ti):
    """Returns dict of horizon -> (mean, n)."""
    out = {}
    for hi, hlbl in enumerate(H_LBLS):
        s = timing_sum[:, di, ci, ti, hi].sum()
        c = timing_cnt[:, di, ci, ti, hi].sum()
        out[hlbl] = (s/c if c > 0 else np.nan, int(c))
    # total N = count from same-bar (horizon 0)
    total_n = timing_cnt[:, di, ci, ti, 0].sum()
    out["_n"] = int(total_n)
    return out

# z-test helper
def z_test_two_prop(n1, p1, n2, p2, sm1, sm2):
    pp = (sm1 + sm2) / (n1 + n2)
    se = np.sqrt(pp*(1-pp)*(1/n1+1/n2))
    z  = (p1 - p2) / se if se > 0 else np.nan
    pv = 2*(1 - sp_stats.norm.cdf(abs(z))) if np.isfinite(z) else np.nan
    return z, pv

# ══════════════════════════════════════════════════════════════════════════════
# PRINT RESULTS
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*68)
print("SECTION 1 — Speed-asymmetry cluster bootstrap (3c, persistent, 30-min)")
print("="*68)

n_kpm_p3 = timing_cnt[:, 0, 0, 0, 0].sum()
n_pmk_p3 = timing_cnt[:, 1, 0, 0, 0].sum()
print(f"  N persistent K->PM: {n_kpm_p3}  PM->K: {n_pmk_p3}")
print(f"  K->PM speed:  {obs_spd_k:.3f}  ({obs_spd_k:.0%})")
print(f"  PM->K speed:  {obs_spd_p:.3f}  ({obs_spd_p:.0%})")
print(f"  Observed diff:{obs_spd_diff:+.3f}")
print(f"  95% CI:       [{lo_spd:+.3f}, {hi_spd:+.3f}]")
print(f"  Bootstrap p:  {p_spd:.4f}")
speed_sig = lo_spd > 0 or hi_spd < 0
print(f"  Result:       {'CI excludes 0 — speed asymmetry significant' if speed_sig else 'CI includes 0 — not established'}")

print("\n" + "="*68)
print("SECTION 2 — Bucket + timing by threshold")
print("="*68)
for ti, thr in enumerate(THRESHOLDS):
    bk = obs_bucket(0, ti); bp = obs_bucket(1, ti)
    print(f"\n  --- Threshold: {thr:.0%} ({thr*100:.0f} cents) ---")
    if bk["n"] < MIN_N or bp["n"] < MIN_N:
        print(f"  WARNING: N={bk['n']} (K->PM) / {bp['n']} (PM->K) — below {MIN_N}, estimates unstable")
    for lbl, b in [("K->PM", bk), ("PM->K", bp)]:
        print(f"  {lbl}  N={b['n']}  same={b['same']} ({b['same_rate']:.1%})  "
              f"zero={b['zero']} ({b['zero_rate']:.1%})  opp={b['opp']} ({b['opp_rate']:.1%})")

    z_, pv_ = z_test_two_prop(bk["n"], bk["same_rate"], bp["n"], bp["same_rate"],
                               bk["same"], bp["same"])
    lo_, hi_, pb_ = (lo_sdr3, hi_sdr3, p_sdr3) if ti==0 else (lo_sdr5, hi_sdr5, p_sdr5)
    print(f"  same-dir diff: {bk['same_rate']-bp['same_rate']:+.3f}  z={z_:.2f}  p={pv_:.4f}  "
          f"boot CI=[{lo_:+.3f},{hi_:+.3f}]  boot-p={pb_:.4f}")

    lo_z_, hi_z_, pz_ = (lo_z3, hi_z3, p_z3) if ti==0 else (lo_z5, hi_z5, p_z5)
    zr_diff = bp["zero_rate"] - bk["zero_rate"]
    print(f"  zero-rate diff(PM-K): {zr_diff:+.3f}  boot CI=[{lo_z_:+.3f},{hi_z_:+.3f}]  boot-p={pz_:.4f}")

    # timing
    for lbl_t, di in [("K->PM", 0), ("PM->K", 1)]:
        print(f"\n  Timing {lbl_t} (>={thr*100:.0f}c):")
        print(f"  {'Class':<12} {'N':>4}  " + "  ".join(f"{h:>8}" for h in H_LBLS))
        for cls, ci in [("PERSISTENT",0),("TRANSIENT",1)]:
            t_ = obs_timing(di, ci, ti)
            n_ = t_["_n"]
            if n_ < MIN_N:
                print(f"  {cls:<12} N={n_} < {MIN_N} — not reported")
                continue
            vals = [t_[h][0] for h in H_LBLS]
            vstr = "  ".join(f"{v:>+8.4f}" if np.isfinite(v) else f"{'n/a':>8}" for v in vals)
            spd_ = vals[H_LBLS.index("+30m")] / vals[H_LBLS.index("+2h")] if vals[H_LBLS.index("+2h")] and vals[H_LBLS.index("+2h")] != 0 else np.nan
            print(f"  {cls:<12} {n_:>4}  {vstr}")
            if cls == "PERSISTENT":
                print(f"  {'':12} {'':>4}  share of +2h at +30m: {spd_:.0%}" if np.isfinite(spd_) else "  n/a")

print(f"\n  Total elapsed: {time.time()-t0:.1f}s")

# ══════════════════════════════════════════════════════════════════════════════
# WRITE MARKDOWN
# ══════════════════════════════════════════════════════════════════════════════
def fv(v, fmt=".3f"):
    return f"{v:{fmt}}" if np.isfinite(v) else "—"

def ci_str(lo, hi):
    return f"[{fv(lo,'+.3f')}, {fv(hi,'+.3f')}]"

def survive(ci_lo, ci_hi):
    return "**YES**" if (ci_lo > 0 or ci_hi < 0) else "no"

# observed values for markdown
bk3 = obs_bucket(0, 0); bp3 = obs_bucket(1, 0)
bk5 = obs_bucket(0, 1); bp5 = obs_bucket(1, 1)
z3, pv3 = z_test_two_prop(bk3["n"], bk3["same_rate"], bp3["n"], bp3["same_rate"], bk3["same"], bp3["same"])
z5, pv5 = z_test_two_prop(bk5["n"], bk5["same_rate"], bp5["n"], bp5["same_rate"], bk5["same"], bp5["same"])

def timing_md_rows(di, ti):
    rows = ""
    for cls, ci in [("PERSISTENT",0),("TRANSIENT",1)]:
        t_ = obs_timing(di, ci, ti)
        n_ = t_["_n"]
        if n_ < MIN_N:
            rows += f"| {cls} | {n_} | ⚠ N<{MIN_N} | — | — | — | — |\n"
            continue
        vals = [t_[h][0] for h in H_LBLS]
        v30 = vals[H_LBLS.index("+30m")]; v2h = vals[H_LBLS.index("+2h")]
        spd_ = f"{v30/v2h:.0%}" if (np.isfinite(v2h) and v2h != 0) else "—"
        cells = " | ".join(fv(v,"+.4f") for v in vals)
        sp_col = spd_ if cls=="PERSISTENT" else "—"
        rows += f"| {cls} | {n_} | {cells} | {sp_col} |\n"
    rows += f"| unc. baseline | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — |\n"
    return rows

# speed at 5c
spd_k5 = obs_timing(0, 0, 1)  # K->PM persistent 5c
spd_p5 = obs_timing(1, 0, 1)  # PM->K persistent 5c
v30k5 = spd_k5["+30m"][0]; v2hk5 = spd_k5["+2h"][0]
v30p5 = spd_p5["+30m"][0]; v2hp5 = spd_p5["+2h"][0]
spd_k5_val = v30k5/v2hk5 if (np.isfinite(v2hk5) and v2hk5 != 0) else np.nan
spd_p5_val = v30p5/v2hp5 if (np.isfinite(v2hp5) and v2hp5 != 0) else np.nan
n_kp5 = spd_k5["_n"]; n_pp5 = spd_p5["_n"]

# bootstrap speed at 5c
ti5_b = 1
m30_k5 = agg_mean(timing_sum[:, 0, 0, ti5_b, H_LBLS.index("+30m")],
                  timing_cnt[:, 0, 0, ti5_b, H_LBLS.index("+30m")], boot_idx)
m2h_k5 = agg_mean(timing_sum[:, 0, 0, ti5_b, H_LBLS.index("+2h")],
                  timing_cnt[:, 0, 0, ti5_b, H_LBLS.index("+2h")], boot_idx)
m30_p5 = agg_mean(timing_sum[:, 1, 0, ti5_b, H_LBLS.index("+30m")],
                  timing_cnt[:, 1, 0, ti5_b, H_LBLS.index("+30m")], boot_idx)
m2h_p5 = agg_mean(timing_sum[:, 1, 0, ti5_b, H_LBLS.index("+2h")],
                  timing_cnt[:, 1, 0, ti5_b, H_LBLS.index("+2h")], boot_idx)
with np.errstate(invalid="ignore", divide="ignore"):
    spd_diff5_boot = np.where(m2h_k5!=0, m30_k5/m2h_k5, np.nan) - np.where(m2h_p5!=0, m30_p5/m2h_p5, np.nan)
lo_spd5, hi_spd5, p_spd5 = boot_ci(spd_diff5_boot, 0)

# summary survive flags
sdr_surv_cluster = lo_sdr3 > 0 or hi_sdr3 < 0
sdr_surv_5c      = lo_sdr5 > 0 or hi_sdr5 < 0
zero_surv_cluster= lo_z3 > 0 or hi_z3 < 0
zero_surv_5c     = lo_z5 > 0 or hi_z5 < 0
spd_surv_cluster = lo_spd > 0 or hi_spd < 0
spd_surv_5c      = (lo_spd5 > 0 or hi_spd5 < 0) if (n_kp5 >= MIN_N and n_pp5 >= MIN_N) else None

def surv_str(b):
    if b is None: return "N<30"
    return "**YES**" if b else "no"

md = f"""# Phase 2 — Asymmetry Robustness Checks
**Generated:** {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
**Panel:** `phase2_full_panel.parquet` — 178 fights, 4 pm_flip excluded
**Bootstrap:** two-stage — per-fight stats computed once; {N_BOOT} resamples of {F} fight rows
**Stratum:** 30-min co-active bars | Jump threshold: 3c or 5c | B={N_BOOT}, seed=42

---

## Section 1 — Speed-asymmetry cluster bootstrap (3c threshold, PERSISTENT jumps)

**Speed** = share of +2h aligned cumulative response already in place at +30m.
Bootstrap resamples fight rows from the {F}-row per-fight summary (no recomputation in loop).

| | K→PM PERSISTENT | PM→K PERSISTENT |
|:--|----------------:|----------------:|
| N jumps used | {int(n_kpm_p3)} | {int(n_pmk_p3)} |
| mean B at +30m | {fv(obs_m30k,'+.4f')} | {fv(obs_m30p,'+.4f')} |
| mean B at +2h  | {fv(obs_m2hk,'+.4f')} | {fv(obs_m2hp,'+.4f')} |
| **Speed (+30m/+2h)** | **{obs_spd_k:.0%}** | **{obs_spd_p:.0%}** |
| Observed diff (K−PM) | **{obs_spd_diff:+.3f}** | |
| 95% bootstrap CI | {ci_str(lo_spd, hi_spd)} | |
| Bootstrap p | {p_spd:.4f} | |
| Result | {'**CI excludes 0 — significant**' if speed_sig else 'CI includes 0 — not established'} | |

---

## Section 2 — Size-conditioned rerun

### 2a — Bucket decomposition

| Threshold | Direction | N | same (%) | zero (%) | opposite (%) | same-diff | boot CI | boot-p |
|:---------:|:----------|--:|---------:|---------:|-------------:|----------:|:-------:|-------:|
| 3c | K→PM | {bk3['n']} | {bk3['same']} ({bk3['same_rate']:.1%}) | {bk3['zero']} ({bk3['zero_rate']:.1%}) | {bk3['opp']} ({bk3['opp_rate']:.1%}) | {bk3['same_rate']-bp3['same_rate']:+.3f} | {ci_str(lo_sdr3,hi_sdr3)} | {p_sdr3:.3f} |
| 3c | PM→K | {bp3['n']} | {bp3['same']} ({bp3['same_rate']:.1%}) | {bp3['zero']} ({bp3['zero_rate']:.1%}) | {bp3['opp']} ({bp3['opp_rate']:.1%}) | | | |
| 5c | K→PM | {bk5['n']} | {bk5['same']} ({bk5['same_rate']:.1%}) | {bk5['zero']} ({bk5['zero_rate']:.1%}) | {bk5['opp']} ({bk5['opp_rate']:.1%}) | {bk5['same_rate']-bp5['same_rate']:+.3f} | {ci_str(lo_sdr5,hi_sdr5)} | {p_sdr5:.3f} |
| 5c | PM→K | {bp5['n']} | {bp5['same']} ({bp5['same_rate']:.1%}) | {bp5['zero']} ({bp5['zero_rate']:.1%}) | {bp5['opp']} ({bp5['opp_rate']:.1%}) | | | |

Zero-rate difference (PM→K minus K→PM): 3c = {bp3['zero_rate']-bk3['zero_rate']:+.3f}, boot CI {ci_str(lo_z3,hi_z3)}, p={p_z3:.3f};  5c = {bp5['zero_rate']-bk5['zero_rate']:+.3f}, boot CI {ci_str(lo_z5,hi_z5)}, p={p_z5:.3f}.

{"⚠ **N < 30 at 5c in one or more cells** — treat estimates as approximate." if bk5['n'] < MIN_N or bp5['n'] < MIN_N else ""}

### 2b — Timing decomposition

Values = B's mean aligned cumulative return. `speed` = mean(+30m)/mean(+2h) for PERSISTENT rows only.

#### 3c threshold

**K→PM**

| Class | N | same | +30m | +1h | +2h | speed |
|:------|--:|-----:|-----:|----:|----:|------:|
{timing_md_rows(0, 0)}
**PM→K**

| Class | N | same | +30m | +1h | +2h | speed |
|:------|--:|-----:|-----:|----:|----:|------:|
{timing_md_rows(1, 0)}
#### 5c threshold

**K→PM**

| Class | N | same | +30m | +1h | +2h | speed |
|:------|--:|-----:|-----:|----:|----:|------:|
{timing_md_rows(0, 1)}
**PM→K**

| Class | N | same | +30m | +1h | +2h | speed |
|:------|--:|-----:|-----:|----:|----:|------:|
{timing_md_rows(1, 1)}
Speed diff at 5c: K→PM {fv(spd_k5_val,'.0%')} vs PM→K {fv(spd_p5_val,'.0%')},
boot CI {ci_str(lo_spd5, hi_spd5)}, p={p_spd5:.4f}.
{"(N_kpm_persistent={}, N_pmk_persistent={})".format(n_kp5, n_pp5) + (" ⚠ N<30" if n_kp5<MIN_N or n_pp5<MIN_N else "")}

---

## Section 3 — Summary: which asymmetries survive?

| Asymmetry | Observed (3c) | (a) Cluster boot | (b) Size >= 5c | (c) Both |
|:----------|:-------------|:----------------|:--------------|:--------:|
| **Same-dir rate** (K→PM > PM→K) | {bk3['same_rate']:.0%} vs {bp3['same_rate']:.0%} (+{(bk3['same_rate']-bp3['same_rate'])*100:.0f}pp) | CI={ci_str(lo_sdr3,hi_sdr3)}, p={p_sdr3:.3f} | CI={ci_str(lo_sdr5,hi_sdr5)}, p={p_sdr5:.3f} | {surv_str(sdr_surv_cluster and sdr_surv_5c)} |
| **Zero-rate** (PM→K >> K→PM) | {bp3['zero_rate']:.0%} vs {bk3['zero_rate']:.0%} (+{(bp3['zero_rate']-bk3['zero_rate'])*100:.0f}pp) | CI={ci_str(lo_z3,hi_z3)}, p={p_z3:.3f} | CI={ci_str(lo_z5,hi_z5)}, p={p_z5:.3f} | {surv_str(zero_surv_cluster and zero_surv_5c)} |
| **Speed** (K→PM faster) | {obs_spd_k:.0%} vs {obs_spd_p:.0%} (+{(obs_spd_k-obs_spd_p)*100:.0f}pp) | CI={ci_str(lo_spd,hi_spd)}, p={p_spd:.3f} | CI={ci_str(lo_spd5,hi_spd5)}, p={p_spd5:.3f} | {surv_str(spd_surv_cluster and (spd_surv_5c if spd_surv_5c is not None else False))} |

### Interpretation

**Same-dir rate:** The K→PM same-direction rate ({bk3['same_rate']:.0%}) exceeds PM→K ({bp3['same_rate']:.0%}) by {(bk3['same_rate']-bp3['same_rate'])*100:.0f}pp at 3c. Bootstrap CI {ci_str(lo_sdr3,hi_sdr3)} {'excludes zero — survives clustering' if sdr_surv_cluster else 'includes zero — does not survive clustering'}. At 5c the CI is {ci_str(lo_sdr5,hi_sdr5)} ({'also significant' if sdr_surv_5c else 'also includes zero'}).

**Zero-rate:** PM→K produces a zero same-bar Kalshi response {bp3['zero_rate']:.0%} of the time vs {bk3['zero_rate']:.0%} for K→PM ({(bp3['zero_rate']-bk3['zero_rate'])*100:.0f}pp gap). Bootstrap CI {ci_str(lo_z3,hi_z3)} — {'survives clustering' if zero_surv_cluster else 'does not survive clustering'}. This reflects Kalshi's discrete cent-grid pricing: PM moves continuously while Kalshi prices round to the nearest cent. Pattern persists at 5c (CI {ci_str(lo_z5,hi_z5)}).

**Speed:** K→PM propagation is faster ({obs_spd_k:.0%} of +2h response in place at +30m) vs PM→K ({obs_spd_p:.0%}). Bootstrap CI {ci_str(lo_spd, hi_spd)} — {'speed asymmetry survives clustering.' if spd_surv_cluster else 'CI includes zero — not statistically established at this N with fight-level clustering.'} At 5c: CI {ci_str(lo_spd5, hi_spd5)} ({'significant' if spd_surv_5c else 'not significant' if spd_surv_5c is not None else 'N<30'}).
"""

QA.write_text(md, encoding="utf-8")
print(f"\nReport written: {QA}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
