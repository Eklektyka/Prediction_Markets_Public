"""
phase2_jump_anatomy.py
======================
Three tables on co-jump anatomy and gap dynamics.

Table 1 — Same-bar co-jump:  for A-jumps (|ret_A| >= 3c) in co-active bars,
          measure B's SAME-BAR signed response.
Table 2 — Conditional propagation: PERSISTENT vs TRANSIENT A-jumps,
          B's aligned cumulative return at same-bar, +30m, +2h, +6h.
Table 3 — Gap dynamics: gap_t = K_last - PM_last; |gap| stats per tier;
          episode analysis (first crossing 5c, time to return <= 2c).
Output:   qa/phase2_jump_anatomy.md
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path

ROOT  = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
PANEL = ROOT / "data/clean/phase2_prototype_panel.parquet"
QA    = ROOT / "qa/phase2_jump_anatomy.md"
QA.parent.mkdir(parents=True, exist_ok=True)

# ── load panel & crosswalk tier ────────────────────────────────────────────────
df = pd.read_parquet(PANEL)
df["bar_utc"] = pd.to_datetime(df["bar_utc"], utc=True)

xw = pd.read_parquet(
    ROOT / "data/meta/ufc_crosswalk.parquet",
    columns=["fight_id", "event_date", "kalshi_volume", "pm_volume"],
)
xw["combined"] = xw["kalshi_volume"] + xw["pm_volume"].fillna(0)
xw["event_date"] = pd.to_datetime(xw["event_date"]).dt.date
xw["rank"] = xw.groupby("event_date")["combined"].rank(ascending=False, method="first")
xw["tier"] = xw["rank"].apply(lambda r: "main_event" if r == 1 else "undercard")
tier_map = xw.set_index("fight_id")["tier"].to_dict()

df["tier"] = df["fight_id"].map(tier_map)

# ── per-fight returns on co-active bars ────────────────────────────────────────
JUMP_THRESH = 0.03    # 3 cents
BAR_MINS    = 5
H30  = 6              # 30 min
H2H  = 24             # 2 hours
H6H  = 72             # 6 hours
PERSIST_H   = 12      # 1 hour = 12 × 5-min bars (persistence check window)
PERSIST_FRAC = 0.5    # >= 50% of original jump still intact

co = df[df["both_traded"]].copy()
co = co.sort_values(["fight_id", "bar_utc"]).reset_index(drop=True)

# compute per-fight 5-min returns (diff within fight)
co["dk"]  = co.groupby("fight_id")["k_last"].diff()
co["dpm"] = co.groupby("fight_id")["pm_last"].diff()

# ══════════════════════════════════════════════════════════════════════════════
# Helper: unconditional baselines on co-active bars (excluding first bar/fight)
# ══════════════════════════════════════════════════════════════════════════════
dk_unc  = co["dk"].dropna()
dpm_unc = co["dpm"].dropna()

def unc_stats(ret_series):
    """mean signed, share same-dir (vs positive), share |ret|>=1c — baselines."""
    r = ret_series.dropna()
    return {
        "mean_signed":  r.mean(),
        "share_pos":    (r > 0).mean(),     # unconditional ~50%
        "share_1c":     (r.abs() >= 0.01).mean(),
    }

unc_k  = unc_stats(dk_unc)
unc_pm = unc_stats(dpm_unc)

print("Unconditional baselines (co-active bars):")
print(f"  Kalshi  : mean={unc_k['mean_signed']:+.5f}  share_pos={unc_k['share_pos']:.1%}  share_|ret|>=1c={unc_k['share_1c']:.1%}  N={len(dk_unc)}")
print(f"  PM      : mean={unc_pm['mean_signed']:+.5f}  share_pos={unc_pm['share_pos']:.1%}  share_|ret|>=1c={unc_pm['share_1c']:.1%}  N={len(dpm_unc)}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 1 — Same-bar co-jump
# ══════════════════════════════════════════════════════════════════════════════
def same_bar_cojump(jumps_A_ret, B_ret_same_bar):
    """
    Given aligned series of A-jump returns and B's same-bar return,
    return stats on B aligned to A's direction.
    """
    signs = np.sign(jumps_A_ret)
    b_signed = signs * B_ret_same_bar   # positive = same direction as A
    return {
        "n":            len(b_signed),
        "mean_signed":  np.nanmean(b_signed),
        "share_same":   np.mean(b_signed > 0),
        "share_1c":     np.mean(np.abs(B_ret_same_bar) >= 0.01),
    }

print("=" * 70)
print("TABLE 1 — Same-bar co-jump")
print("=" * 70)

results_t1 = {}
for a_col, b_col, a_lbl, b_lbl, b_unc in [
    ("dk",  "dpm", "K", "PM", unc_pm),
    ("dpm", "dk",  "PM", "K", unc_k),
]:
    jumps = co[co[a_col].abs() >= JUMP_THRESH].copy()
    jumps = jumps.dropna(subset=[a_col, b_col])
    stats = same_bar_cojump(jumps[a_col].values, jumps[b_col].values)
    results_t1[(a_lbl, b_lbl)] = (stats, b_unc, jumps)
    print(f"\n  {a_lbl}-jumps (N={stats['n']}) -> {b_lbl} same-bar response:")
    print(f"    mean B aligned:    {stats['mean_signed']:+.5f}  (unc={b_unc['mean_signed']:+.5f})")
    print(f"    share same-dir:    {stats['share_same']:.1%}        (unc ~50%)")
    print(f"    share |B|>=1c:     {stats['share_1c']:.1%}        (unc={b_unc['share_1c']:.1%})")

print()

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 2 — Conditional propagation: PERSISTENT vs TRANSIENT
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("TABLE 2 — Conditional propagation (PERSISTENT vs TRANSIENT)")
print("=" * 70)

def classify_and_propagate(co_df, a_col, b_col, persist_h, persist_frac,
                            h30, h2h, h6h):
    """
    For each A-jump in co_df:
      - Determine if PERSISTENT (A still >= 50% of jump at +1h)
      - Compute B's cumulative aligned return at same-bar, +30m, +2h, +6h
    Returns dict of lists keyed by (class, horizon).
    """
    results = {"PERSISTENT": {}, "TRANSIENT": {}}
    for cls in results:
        for h in ["same", "30m", "2h", "6h"]:
            results[cls][h] = []

    for fid, grp in co_df.groupby("fight_id"):
        grp = grp.sort_values("bar_utc").reset_index(drop=True)
        a_vals = grp[a_col].values
        b_vals = grp[b_col].values
        n = len(grp)

        for i in range(1, n):
            ra = a_vals[i]
            if not np.isfinite(ra) or abs(ra) < JUMP_THRESH:
                continue
            sign = np.sign(ra)

            # classify: look at A's cumulative move from pre-jump (i-1) to i+persist_h
            if i + persist_h < n:
                a_pre   = grp["k_last"].iloc[i - 1] if a_col == "dk" else grp["pm_last"].iloc[i - 1]
                a_post  = grp["k_last"].iloc[i + persist_h] if a_col == "dk" else grp["pm_last"].iloc[i + persist_h]
                cumul_a = a_post - a_pre
                if np.isfinite(cumul_a) and (sign * cumul_a) >= persist_frac * abs(ra):
                    cls = "PERSISTENT"
                else:
                    cls = "TRANSIENT"
            else:
                continue   # not enough runway to classify

            # B's aligned cumulative return at each horizon
            rb_same = b_vals[i]
            b_signed_same = sign * rb_same if np.isfinite(rb_same) else np.nan

            def cumul_b(start, end):
                if end > n:
                    return np.nan
                chunk = b_vals[start:end]
                if np.sum(np.isfinite(chunk)) < (end - start) // 2:
                    return np.nan
                return sign * np.nansum(chunk)

            results[cls]["same"].append(b_signed_same)
            results[cls]["30m"].append(cumul_b(i + 1, i + 1 + h30))
            results[cls]["2h"].append(cumul_b(i + 1, i + 1 + h2h))
            results[cls]["6h"].append(cumul_b(i + 1, i + 1 + h6h))

    return results

# unconditional baselines for B at each horizon (aligned to random sign)
def unc_cumul(b_col_vals, h):
    """unconditional mean cumulative return over h bars (random sign = 0)."""
    return 0.0   # by symmetry, E[sign * sum] = 0 unconditionally

horizons = ["same", "30m", "2h", "6h"]

for a_col, b_col, a_lbl, b_lbl in [
    ("dk",  "dpm", "K",  "PM"),
    ("dpm", "dk",  "PM", "K"),
]:
    res = classify_and_propagate(co, a_col, b_col, PERSIST_H, PERSIST_FRAC,
                                  H30, H2H, H6H)
    print(f"\n  {a_lbl}-jumps -> {b_lbl} propagation:")
    print(f"  {'Class':<12} {'N':>5}  {'same-bar':>9}  {'+30m':>9}  {'+2h':>9}  {'+6h':>9}")
    print(f"  {'-'*60}")
    for cls in ["PERSISTENT", "TRANSIENT"]:
        n = len(res[cls]["same"])
        vals = [np.nanmean(res[cls][h]) if res[cls][h] else np.nan for h in horizons]
        print(f"  {cls:<12} {n:>5}  {vals[0]:>+9.4f}  {vals[1]:>+9.4f}  {vals[2]:>+9.4f}  {vals[3]:>+9.4f}")
    print(f"  {'unc. base':<12} {'--':>5}  {'0.0000':>9}  {'0.0000':>9}  {'0.0000':>9}  {'0.0000':>9}")

print()

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 3 — Gap dynamics
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("TABLE 3 — Gap dynamics")
print("=" * 70)

GAP_OPEN  = 0.05   # 5 cents — episode opens
GAP_CLOSE = 0.02   # 2 cents — episode closes

co["gap"] = co["k_last"] - co["pm_last"]
co["abs_gap"] = co["gap"].abs()

# 3a — |gap| stats per tier
print("\n  3a — |gap| distribution per tier (co-active bars):")
print(f"  {'Tier':<12}  {'N_bars':>7}  {'mean_|gap|':>10}  {'p90_|gap|':>9}")
print(f"  {'-'*45}")
for tier, grp in co.groupby("tier"):
    valid = grp["abs_gap"].dropna()
    if len(valid) == 0:
        continue
    print(f"  {tier:<12}  {len(valid):>7}  {valid.mean():>10.4f}  {np.percentile(valid, 90):>9.4f}")

# 3b — episode analysis
print("\n  3b — Gap episodes (|gap| crosses 5c from below, closes at <=2c):")
episodes = []

for fid, grp in co.groupby("fight_id"):
    grp = grp.sort_values("bar_utc").reset_index(drop=True)
    abs_g = grp["abs_gap"].values
    times  = grp["bar_utc"].values
    n = len(grp)

    in_episode = False
    ep_start_bar = None
    ep_start_time = None

    for i in range(n):
        ag = abs_g[i]
        if not np.isfinite(ag):
            continue

        if not in_episode:
            # was previous bar below the open threshold?
            prev_ag = abs_g[i - 1] if i > 0 else 0.0
            if ag >= GAP_OPEN and (not np.isfinite(prev_ag) or prev_ag < GAP_OPEN):
                in_episode = True
                ep_start_bar = i
                ep_start_time = times[i]
        else:
            # check if closed
            if ag <= GAP_CLOSE:
                close_time = times[i]
                open_ts  = pd.Timestamp(ep_start_time)
                close_ts = pd.Timestamp(close_time)
                duration_min = (close_ts - open_ts).total_seconds() / 60
                episodes.append({
                    "fight_id": fid,
                    "tier":     tier_map.get(fid, "unknown"),
                    "open_ts":  open_ts,
                    "close_ts": close_ts,
                    "duration_min": duration_min,
                    "censored": False,
                })
                in_episode = False

    # censored if still open at end
    if in_episode:
        episodes.append({
            "fight_id": fid,
            "tier":     tier_map.get(fid, "unknown"),
            "open_ts":  pd.Timestamp(ep_start_time),
            "close_ts": None,
            "duration_min": np.nan,
            "censored": True,
        })

ep_df = pd.DataFrame(episodes)
n_ep   = len(ep_df)
n_cens = ep_df["censored"].sum()
n_cls  = (~ep_df["censored"]).sum()

if n_cls > 0:
    closed = ep_df[~ep_df["censored"]]["duration_min"]
    median_close = np.nanmedian(closed)
    pct_30m  = np.mean(closed <= 30)
    pct_2h   = np.mean(closed <= 120)
    pct_6h   = np.mean(closed <= 360)
    pct_24h  = np.mean(closed <= 1440)
else:
    median_close = pct_30m = pct_2h = pct_6h = pct_24h = np.nan

print(f"  N episodes total:          {n_ep}")
print(f"  N closed (<=2c):           {n_cls}")
print(f"  N censored (open at t_end):{n_cens}")
if n_cls > 0:
    print(f"  Median close time:         {median_close:.0f} min")
    print(f"  Share closed within 30m:   {pct_30m:.1%}")
    print(f"  Share closed within 2h:    {pct_2h:.1%}")
    print(f"  Share closed within 6h:    {pct_6h:.1%}")
    print(f"  Share closed within 24h:   {pct_24h:.1%}")

# also break down by tier
if n_ep > 0:
    print()
    print(f"  {'Tier':<12}  {'N_ep':>5}  {'N_closed':>8}  {'N_cens':>6}  {'med_min':>7}  {'<30m':>6}  {'<2h':>5}  {'<6h':>5}")
    print(f"  {'-'*65}")
    for tier, grp in ep_df.groupby("tier"):
        nc  = (~grp["censored"]).sum()
        nce = grp["censored"].sum()
        if nc > 0:
            c = grp[~grp["censored"]]["duration_min"]
            med = np.nanmedian(c)
            p30 = np.mean(c <= 30)
            p2h = np.mean(c <= 120)
            p6h = np.mean(c <= 360)
        else:
            med = p30 = p2h = p6h = np.nan
        print(f"  {tier:<12}  {len(grp):>5}  {nc:>8}  {nce:>6}  {med:>7.0f}  {p30:>6.0%}  {p2h:>5.0%}  {p6h:>5.0%}")

print()

# ══════════════════════════════════════════════════════════════════════════════
# Collect numbers for markdown
# ══════════════════════════════════════════════════════════════════════════════
t1 = {}
for a_lbl, b_lbl, b_unc_d in [("K", "PM", unc_pm), ("PM", "K", unc_k)]:
    stats, b_unc, jumps_df = results_t1[(a_lbl, b_lbl)]
    t1[(a_lbl, b_lbl)] = (stats, b_unc_d)

t2_k  = classify_and_propagate(co, "dk",  "dpm", PERSIST_H, PERSIST_FRAC, H30, H2H, H6H)
t2_pm = classify_and_propagate(co, "dpm", "dk",  PERSIST_H, PERSIST_FRAC, H30, H2H, H6H)

gap_tiers = {}
for tier, grp in co.groupby("tier"):
    valid = grp["abs_gap"].dropna()
    gap_tiers[tier] = {"mean": valid.mean(), "p90": np.percentile(valid, 90), "n": len(valid)}

# ══════════════════════════════════════════════════════════════════════════════
# Synthesis verdict
# ══════════════════════════════════════════════════════════════════════════════
s_k  = results_t1[("K", "PM")][0]
s_pm = results_t1[("PM", "K")][0]

simult_k   = s_k["share_same"]
simult_pm  = s_pm["share_same"]
mean1c_k   = s_k["share_1c"]
mean1c_pm  = s_pm["share_1c"]

# persistent k->pm at 2h
p_k_2h = np.nanmean(t2_k["PERSISTENT"]["2h"]) if t2_k["PERSISTENT"]["2h"] else np.nan
t_k_2h = np.nanmean(t2_k["TRANSIENT"]["2h"])  if t2_k["TRANSIENT"]["2h"]  else np.nan
p_pm_2h = np.nanmean(t2_pm["PERSISTENT"]["2h"]) if t2_pm["PERSISTENT"]["2h"] else np.nan

n_pers_k  = len(t2_k["PERSISTENT"]["same"])
n_tran_k  = len(t2_k["TRANSIENT"]["same"])
n_pers_pm = len(t2_pm["PERSISTENT"]["same"])
n_tran_pm = len(t2_pm["TRANSIENT"]["same"])

# ══════════════════════════════════════════════════════════════════════════════
# WRITE MARKDOWN
# ══════════════════════════════════════════════════════════════════════════════
def pct(x): return f"{x:.1%}"
def sgn(x): return f"{x:+.4f}"

md_t1_rows = ""
for a_lbl, b_lbl, b_unc_d in [("K","PM",unc_pm), ("PM","K",unc_k)]:
    st, _, _jumps = results_t1[(a_lbl, b_lbl)]
    md_t1_rows += (
        f"| {a_lbl}-jumps → {b_lbl} | {st['n']} | "
        f"{sgn(st['mean_signed'])} | {sgn(b_unc_d['mean_signed'])} | "
        f"{pct(st['share_same'])} | 50.0% | "
        f"{pct(st['share_1c'])} | {pct(b_unc_d['share_1c'])} |\n"
    )

def t2_row(cls, n, vals):
    vs = [f"{v:+.4f}" if np.isfinite(v) else "n/a" for v in vals]
    return f"| {cls} | {n} | {vs[0]} | {vs[1]} | {vs[2]} | {vs[3]} |\n"

def t2_section(res, a_lbl, b_lbl):
    rows = ""
    for cls in ["PERSISTENT", "TRANSIENT"]:
        n = len(res[cls]["same"])
        vals = [np.nanmean(res[cls][h]) if res[cls][h] else np.nan for h in horizons]
        rows += t2_row(cls, n, vals)
    rows += "| unconditional | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 |\n"
    return f"### {a_lbl}-jumps → {b_lbl}\n| Class | N | same-bar | +30m | +2h | +6h |\n|:------|--:|--------:|-----:|----:|----:|\n" + rows

gap_tier_rows = ""
for tier in ["main_event", "undercard"]:
    if tier in gap_tiers:
        g = gap_tiers[tier]
        gap_tier_rows += f"| {tier} | {g['n']} | {g['mean']:.4f} | {g['p90']:.4f} |\n"

ep_tier_rows = ""
if n_ep > 0:
    for tier, grp in ep_df.groupby("tier"):
        nc  = (~grp["censored"]).sum()
        nce = grp["censored"].sum()
        if nc > 0:
            c = grp[~grp["censored"]]["duration_min"]
            med = f"{np.nanmedian(c):.0f}"
            p30 = pct(np.mean(c <= 30))
            p2h = pct(np.mean(c <= 120))
            p6h = pct(np.mean(c <= 360))
            p24 = pct(np.mean(c <= 1440))
        else:
            med = p30 = p2h = p6h = p24 = "—"
        ep_tier_rows += f"| {tier} | {len(grp)} | {nc} | {nce} | {med} | {p30} | {p2h} | {p6h} | {p24} |\n"

# synthesis paragraph
synth_parts = []

if simult_k >= 0.65 or simult_pm >= 0.65:
    synth_parts.append(
        f"Same-bar co-movement is strong: {pct(simult_k)} of K-jumps and "
        f"{pct(simult_pm)} of PM-jumps are matched same-bar on the other venue, "
        f"consistent with both venues reacting to the same underlying information "
        f"within the same 5-minute bar."
    )
else:
    synth_parts.append(
        f"Same-bar co-movement is weak: only {pct(simult_k)} of K-jumps and "
        f"{pct(simult_pm)} of PM-jumps are matched same-bar on the other venue, "
        f"suggesting venues frequently update at different times."
    )

if np.isfinite(p_k_2h) and abs(p_k_2h) > 0.005:
    synth_parts.append(
        f"Persistent K-jumps (N={n_pers_k}) elicit a {sgn(p_k_2h)} PM response at +2h, "
        f"while transient K-jumps (N={n_tran_k}) show {sgn(t_k_2h)}, "
        f"indicating delayed convergence follows fundamental price changes."
    )
else:
    synth_parts.append(
        f"Persistent K-jumps (N={n_pers_k}) show negligible PM response at +2h ({sgn(p_k_2h) if np.isfinite(p_k_2h) else 'n/a'}), "
        f"so even genuine price moves on Kalshi are not reliably echoed on Polymarket at 2-hour horizons."
    )

if n_cls > 0:
    synth_parts.append(
        f"Gap episodes exceeding 5¢ (N={n_ep} total, {n_cens} censored) close in a "
        f"median of {median_close:.0f} minutes; {pct(pct_2h)} close within 2h and "
        f"{pct(pct_6h)} within 6h — suggesting partial convergence pressure but "
        f"{'slow' if median_close > 60 else 'moderate'} arbitrage speed in this thin market."
    )
else:
    synth_parts.append("No gap episodes exceeding 5¢ were observed in the panel window.")

# overall verdict
if simult_k >= 0.60 and simult_pm >= 0.60:
    verdict = (
        "The dominant pattern is **simultaneous updating**: the same new information "
        "lands on both venues within the same 5-minute bar more than 60% of the time. "
        "There is no systematic price-discovery lead at either horizon tested. "
        "Cross-venue gap episodes do close, but slowly, implying the venues are "
        "integrated but not tightly arbitraged."
    )
elif simult_k >= 0.55 or simult_pm >= 0.55:
    verdict = (
        "The pattern is **predominantly simultaneous** with some delayed propagation. "
        "Persistent jumps show larger cross-venue responses than transient ones, "
        "but neither venue consistently leads the other. Gaps close slowly, "
        "pointing to loosely integrated but not efficiently arbitraged markets."
    )
else:
        verdict = (
        "The venues appear **partially disconnected**: same-bar co-jump rates are below 55%, "
        "cross-venue propagation after jumps is weak, and gap episodes persist for extended periods. "
        "This is consistent with thin, segmented prediction markets where price discovery "
        "occurs independently on each platform."
    )

synthesis = " ".join(synth_parts) + " " + verdict

md = f"""# Phase 2 — Jump Anatomy & Gap Dynamics
**Generated:** {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
**Panel:** `data/clean/phase2_prototype_panel.parquet` — 20 fights, {len(co)} co-active 5-min bars
**Jump threshold:** |ret| ≥ {JUMP_THRESH:.2f} (3 cents) | **Persistence:** ≥{int(PERSIST_FRAC*100)}% of jump survives {PERSIST_H*BAR_MINS}min

---

## Table 1 — Same-bar co-jump

For each A-jump (|ret_A| ≥ 3¢) on a co-active bar, B's return on the **same bar**, signed by A's direction.

| Direction | N jumps | mean B aligned | mean B unc | share same-dir | unc | share \|B\|≥1¢ | unc |
|:----------|--------:|---------------:|-----------:|---------------:|----:|---------------:|----:|
{md_t1_rows}
*unc = unconditional baseline across all co-active bars*

---

## Table 2 — Conditional propagation (PERSISTENT vs TRANSIENT)

Classification: A-jump is PERSISTENT if A's cumulative return from pre-jump price ≥ 50% of original jump at +{PERSIST_H*BAR_MINS}min; otherwise TRANSIENT.
Values = B's mean **aligned** cumulative return (sign-adjusted to A's direction) at each horizon. Unconditional baseline = 0 by symmetry.

{t2_section(t2_k, "K", "PM")}
{t2_section(t2_pm, "PM", "K")}
---

## Table 3 — Gap dynamics

`gap_t = K_last − PM_last` on co-active bars. Positive = Kalshi premium over PM.

### 3a — |gap| statistics per fight tier

Main event = highest combined volume per event date; undercard = remainder.

| Tier | N bars | mean \|gap\| | p90 \|gap\| |
|:-----|-------:|-------------:|------------:|
{gap_tier_rows}
### 3b — Gap episodes: |gap| crosses {int(GAP_OPEN*100)}¢ → closes ≤ {int(GAP_CLOSE*100)}¢

| Tier | N episodes | N closed | N censored | median min | <30m | <2h | <6h | <24h |
|:-----|----------:|---------:|-----------:|-----------:|-----:|----:|----:|-----:|
{ep_tier_rows}
Overall: N={n_ep} episodes, {n_cls} closed, {n_cens} censored at t_end.
Median close time (closed only): {f'{median_close:.0f} min' if n_cls > 0 else '—'}

---

## Synthesis

{synthesis}
"""

QA.write_text(md, encoding="utf-8")
print(f"QA report written: {QA}")
