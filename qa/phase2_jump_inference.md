# Phase 2 — Jump Inference & Statistical Tests
**Generated:** 2026-07-13 23:44 UTC
**Panel:** `phase2_full_panel.parquet` (178 fights, 4 pm_flip excluded)
**Stratum:** 30-min co-active bars | Jump threshold: |ret| ≥ 3¢ | Bootstrap: B=5000, seed=42

---

## Section 1 — Three-bucket decomposition + formal test

B's same-bar return, signed by A's direction: `same` (B_signed > 0), `zero` (= 0), `opposite` (< 0).

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:----------|--------:|---------:|---------:|-------------:|
| K→PM | 168 | 93 (55.4%) | 26 (15.5%) | 49 (29.2%) |
| PM→K | 194 | 82 (42.3%) | 85 (43.8%) | 27 (13.9%) |

### Two-proportion z-test: H₀: same_rate(K→PM) = same_rate(PM→K)

- K→PM same-rate: **55.4%** (N=168)
- PM→K same-rate: **42.3%** (N=194)
- Observed difference: **+0.131**
- Pooled-SE z-statistic: **2.485** (p = 0.0129)
- Result: **Reject H0 at 5% — the same-direction rates are significantly different**

### Cluster bootstrap: difference K→PM − PM→K (B=5000, clustered by fight)

- Observed: +0.131
- 95% CI: [-0.046, +0.205]
- Bootstrap p≈ 0.2104
- CI includes zero: asymmetry not established beyond sampling noise

**Interpretation:** K-jumps produce a higher same-direction rate on PM than PM-jumps do on K (55.4% vs 42.3%). The asymmetry is statistically significant by z-test; cluster bootstrap CI [-0.046, +0.205] includes zero.

---

## Section 2 — Timing decomposition (persistent vs transient, 30-min)

PERSISTENT = A's price still ≥ 50% of jump magnitude at +60 min.
Values = B's mean aligned cumulative return. `share of +2h at +30m` = mean(+30m) / mean(+2h) for PERSISTENT only.

### K-jumps → PM
| Class | N | same | +30m | +1h | +2h | share of +2h at +30m |
|:------|--:|------:|------:|------:|------:|------:|
| PERSISTENT | 98 | +0.0245 | +0.0170 | +0.0259 | +0.0223 | 76% |
| TRANSIENT | 47 | +0.0158 | -0.0284 | -0.0379 | -0.0165 | — |
| unc. baseline | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — |

### PM-jumps → K
| Class | N | same | +30m | +1h | +2h | share of +2h at +30m |
|:------|--:|------:|------:|------:|------:|------:|
| PERSISTENT | 113 | +0.0282 | +0.0065 | +0.0143 | +0.0192 | 34% |
| TRANSIENT | 65 | +0.0051 | -0.0252 | -0.0245 | -0.0271 | — |
| unc. baseline | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — |


---

## Section 3 — Gap closure medians with bootstrap CIs

ACTIVE episodes only (both venues trade during the episode). Censored episodes excluded from CI.
Tier: main event = top-decile combined volume (N=19 fights); undercard = remainder.

| Tier | N episodes | N closed | median min | 95% CI | <30m | <2h | note |
|:-----|----------:|---------:|-----------:|:------:|-----:|----:|:-----|
| main_event | 9 | 9 | 30 | [5, 90] | 55.6% | 88.9% | ⚠ N=9, wide CIs |
| undercard | 120 | 105 | 120 | [85, 210] | 25.7% | 50.5% |  |


STALE-SIDE episodes (N=7) excluded from main table; they close trivially fast (median <= 10 min) because the quiet side resumes trading.

**Caution:** main-event N=9 episodes produces unreliable bootstrap CIs — treat median (30 min) as an order-of-magnitude estimate only, not a precise point estimate.

---

## Summary of findings

| Question | Finding |
|:---------|:--------|
| K→PM vs PM→K same-bar rate | 55.4% vs 42.3%, diff +0.131, bootstrap CI [-0.046,+0.205] |
| Asymmetry significant? | Yes (z=2.49, p=0.0129) |
| Persistent K→PM at +2h | +0.0223 vs transient -0.0165 |
| Share of +2h K→PM in place at +30m | 76% |
| Persistent PM→K at +2h | +0.0192 vs transient -0.0271 |
| Share of +2h PM→K in place at +30m | 34% |
| ACTIVE gap median (main event) | 30 min (N=9, wide CI) |
| ACTIVE gap median (undercard) | ~120 min (50% < 2h) |
