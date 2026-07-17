# Phase 2 — Asymmetry Robustness v2 (Combined Panel)
**Generated:** 2026-07-14 15:02 UTC
**Panel:** data/clean/phase2_full_panel.parquet — 281 fights (HARFER excluded, pm_flip already baked in)
**Bootstrap:** two-stage, B=500, seed=42, fight-level clustering (resample fight rows)
**Stratum:** 30-min co-active bars

---

## Results

| era | thresh | K->PM N | K->PM same | PM->K N | PM->K same | diff | CI [2.5,97.5] | p | survives clustering? |
|:----|:------:|--------:|-----------:|--------:|-----------:|-----:|:-------------:|--:|:-------------------:|
| pooled         | 3c | 219 | 55.7% | 237 | 43.0% | +12.7pp | [+0.026,+0.231] | 0.012 | **YES** |
| pooled         | 5c | 110 | 53.6% |  81 | 55.6% |  -1.9pp | [-0.154,+0.130] | 0.804 | no |
| 2025_lychee    | 3c | 183 | 53.0% | 197 | 41.6% | +11.4pp | [+0.004,+0.216] | 0.044 | **YES** |
| 2025_lychee    | 5c | 100 | 52.0% |  64 | 56.2% |  -4.2pp | [-0.204,+0.114] | 0.624 | no |
| 2026_collector | 3c |  36 | 69.4% |  40 | 50.0% | +19.4pp | [-0.023,+0.374] | 0.076 | **no** (N=36, CI barely misses 0) |
| 2026_collector | 5c |  10 | 70.0% |  17 | 52.9% | +17.1pp | [-0.222,+0.490] | 0.340 | no (N=10) |

---

## Verdicts

### Pooled
- **3c survives clustering: YES** (p=0.012, CI excludes 0). K→PM same-dir rate 55.7% vs PM→K 43.0%, +12.7pp.
- **5c does NOT survive:** 5c reverses sign (-1.9pp, p=0.804). The asymmetry is a small-jump phenomenon.
- **Overall: pooled asymmetry established at 3c, not size-conditioned.**

### 2025_lychee
- **3c survives clustering: YES** (p=0.044, CI [+0.004, +0.216] just above 0). Replicates pooled finding.
- **5c does NOT survive** (-4.2pp, p=0.624).
- **Verdict: consistent with 2025-only freeze. Asymmetry holds at 3c within era.**

### 2026_collector
- **3c: does NOT survive fight-clustered bootstrap** (p=0.076, CI [-0.023, +0.374] includes 0).
  - Point estimate is larger (+19.4pp, 69.4% vs 50.0%) but N=36 K→PM jumps across only ~91 fights.
  - Underpowered: fight-level clustering inflates CIs when N_fights is small.
- **5c: N=10 K→PM jumps — too sparse for any inference.**
- **Verdict: 2026 69.4% is a pending result. Direction is consistent but does not survive fight-clustered bootstrap with current N. More events needed.**

---

## Note on Exhibit 3 (ex3_jump.md)

The 2026_collector 69.4% K→PM same-dir cell (Panel D, >=3c) should be read with this caveat:
> *2026_collector: point estimate 69.4% (K→PM) vs 50.0% (PM→K), +19.4pp, but fight-clustered bootstrap CI [-0.023, +0.374], p=0.076 — does not survive clustering at N=36 jumps / 91 fights. Pending more 2026 data.*

The pooled result (55.7% vs 43.0%, +12.7pp, p=0.012) survives clustering and is dominated by the 2025_lychee era (N=183/197 jumps, 134 fights).
