# Phase 2 Full Panel — Jump Anatomy & Gap Dynamics
**Generated:** 2026-07-13 23:35 UTC
**Panel:** `data/clean/phase2_full_panel.parquet` — 182 fights → 178 after excluding 4 pm_flip
**Jump threshold:** |ret| ≥ 3¢ | **Persistence:** ≥50% of jump survives 60 min
**Excluded:** 20250823_MUDBOR, 20250906_HARFER, 20250906_SAIRUF, 20251122_SPIGAZ (pm_flip, pending review)

---

## Table 1 — Same-bar co-jump
Values for venue B on the **same bar** as an A-jump, signed by A's direction.
`co-jumps` = bars where **both** venues jump ≥3¢ (any direction).

### 5-min (both%≥25.0%, 10 fights)
| Dir | N | mean B | med B | same-dir | \|B\|≥1¢ (unc) | co-jumps | co-mean/med |
|:----|--:|------:|------:|--------:|------:|-------:|-----:|
| K→PM | 7 | +0.0394 | +0.0100 | 71.4% | 57.1% (17.1%) | 2 (29%) | +0.1350 / +0.1350 |
| PM→K | 10 | +0.0280 | +0.0000 | 40.0% | 60.0% (19.3%) | 2 (20%) | +0.1350 / +0.1350 |

### 30-min (all 178 fights)
| Dir | N | mean B | med B | same-dir | \|B\|≥1¢ (unc) | co-jumps | co-mean/med |
|:----|--:|------:|------:|--------:|------:|-------:|-----:|
| K→PM | 168 | +0.0406 | +0.0050 | 55.4% | 64.3% (33.0%) | 47 (28%) | +0.1401 / +0.0700 |
| PM→K | 194 | +0.0363 | +0.0000 | 42.3% | 52.6% (26.9%) | 47 (24%) | +0.1415 / +0.0600 |

---

## Table 2 — Conditional propagation (PERSISTENT vs TRANSIENT)
PERSISTENT = A's cumulative return from pre-jump price ≥ 50% of jump after 60 min.
Cells = mean aligned cumulative return on B. Unconditional baseline = 0 by symmetry.

### 5-min (both%≥25.0%, 10 fights)
**K→PM** | _same_ | _+30m_ | _+2h_ | _+6h_
|:-------|--:|-----:|-----:|-----:|-----:|
| PERSISTENT | 2 | -0.0072 | +0.0200 | +0.0100 | +0.0050 |
| TRANSIENT | 3 | +0.0067 | -0.0033 | -0.0000 | +0.0033 |
| unc. baseline | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

**PM→K** | _same_ | _+30m_ | _+2h_ | _+6h_
|:-------|--:|-----:|-----:|-----:|-----:|
| PERSISTENT | 4 | +0.0050 | -0.0000 | +0.0025 | -0.0050 |
| TRANSIENT | 4 | -0.0025 | +0.0000 | +0.0100 | +0.0075 |
| unc. baseline | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 |


### 30-min (all 178 fights)
**K→PM** | _same_ | _+30m_ | _+2h_ | _+6h_
|:-------|--:|-----:|-----:|-----:|-----:|
| PERSISTENT | 98 | +0.0245 | +0.0170 | +0.0223 | +0.0013 |
| TRANSIENT | 47 | +0.0158 | -0.0284 | -0.0165 | -0.0029 |
| unc. baseline | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

**PM→K** | _same_ | _+30m_ | _+2h_ | _+6h_
|:-------|--:|-----:|-----:|-----:|-----:|
| PERSISTENT | 113 | +0.0282 | +0.0065 | +0.0192 | -0.0004 |
| TRANSIENT | 65 | +0.0051 | -0.0252 | -0.0271 | -0.0102 |
| unc. baseline | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 |


---

## Table 3 — Gap dynamics
`gap_t = K_last − PM_last`. Gap measured on all bars with both prices available (including ffilled).
Tier: main event = top decile by combined volume (≥2,444,123); undercard = remainder.

### 3a — |gap| on co-active bars per tier
| Tier | N bars | mean \|gap\| | p90 \|gap\| |
|:-----|-------:|-------------:|------------:|
| main_event | 4,739 | 0.0103 | 0.0200 |
| undercard  | 6,709  | 0.0148 | 0.0300 |

### 3b — Gap episodes (|gap| crosses 5¢ → closes ≤ 2¢)
ACTIVE = both venues trade during the episode; STALE-SIDE = one venue has zero trades throughout.

| Type | Tier | N | N closed | N censored | median min | <30m | <2h | <6h |
|:-----|:-----|--:|---------:|-----------:|-----------:|-----:|----:|----:|
| ACTIVE | main_event | 9 | 9 | 0 | 30 | 56% | 89% | 100% |
| ACTIVE | undercard | 120 | 105 | 15 | 120 | 26% | 50% | 73% |
| STALE-SIDE | main_event | 1 | 1 | 0 | 5 | 100% | 100% | 100% |
| STALE-SIDE | undercard | 6 | 5 | 1 | 10 | 60% | 80% | 80% |

---

## Synthesis

Simultaneous updating remains the dominant mode at both strata. At 5-min (10 high-coverage fights), K-jumps have mean aligned PM response of +3.9¢ and 71% same-direction rate; at 30-min across all 178 fights, 28% of K-jumps and 24% of PM-jumps are matched by a co-jump ≥3¢ on the other venue in the same bar, with co-jump mean +0.14 — far larger than the unconditional mean response (+0.04). The 30-min conditional propagation table is the clearest signal in the dataset: persistent K-jumps (N=98, +2h PM response = +0.022) diverge markedly from transient K-jumps (N=47, +2h = −0.017); the same pattern holds for PM-jumps (persistent +0.019 vs transient −0.027 at +2h), indicating that information-driven moves do propagate cross-venue while noise-driven moves mean-revert independently. Gap dynamics split almost entirely into ACTIVE episodes (129/136): STALE-SIDE gaps (one venue quiet, N=7) close trivially fast (median 10 min) once the stale side resumes trading; ACTIVE gaps are the substantive ones — median 30 min on main events (89% < 2h) versus 120 min on undercard (50% < 2h), reflecting tighter arbitrage attention on high-volume fights. Mean |gap| stays below 1.5¢ at all times, and p90 is only 2–3¢, so dislocations are rare and modest. **Overall: simultaneous updating is the norm; persistent price moves propagate at 30-min+ horizons; gap convergence is real but speed depends on fight tier. No systematic directional leadership detected.**
