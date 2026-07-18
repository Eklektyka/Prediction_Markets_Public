# Phase 2 — Jump Anatomy & Gap Dynamics
**Generated:** 2026-07-13 23:19 UTC
**Panel:** `data/clean/phase2_prototype_panel.parquet` — 20 fights, 4869 co-active 5-min bars
**Jump threshold:** |ret| ≥ 0.03 (3 cents) | **Persistence:** ≥50% of jump survives 60min

---

## Table 1 — Same-bar co-jump

For each A-jump (|ret_A| ≥ 3¢) on a co-active bar, B's return on the **same bar**, signed by A's direction.

| Direction | N jumps | mean B aligned | mean B unc | share same-dir | unc | share \|B\|≥1¢ | unc |
|:----------|--------:|---------------:|-----------:|---------------:|----:|---------------:|----:|
| K-jumps → PM | 27 | +0.0371 | -0.0002 | 55.6% | 50.0% | 55.6% | 18.8% |
| PM-jumps → K | 29 | +0.0352 | -0.0002 | 41.4% | 50.0% | 51.7% | 22.1% |

*unc = unconditional baseline across all co-active bars*

---

## Table 2 — Conditional propagation (PERSISTENT vs TRANSIENT)

Classification: A-jump is PERSISTENT if A's cumulative return from pre-jump price ≥ 50% of original jump at +60min; otherwise TRANSIENT.
Values = B's mean **aligned** cumulative return (sign-adjusted to A's direction) at each horizon. Unconditional baseline = 0 by symmetry.

### K-jumps → PM
| Class | N | same-bar | +30m | +2h | +6h |
|:------|--:|--------:|-----:|----:|----:|
| PERSISTENT | 9 | +0.0015 | -0.0022 | +0.0000 | +0.0100 |
| TRANSIENT | 12 | +0.0049 | -0.0016 | -0.0049 | -0.0026 |
| unconditional | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### PM-jumps → K
| Class | N | same-bar | +30m | +2h | +6h |
|:------|--:|--------:|-----:|----:|----:|
| PERSISTENT | 12 | +0.0042 | -0.0025 | -0.0475 | -0.0038 |
| TRANSIENT | 11 | +0.0055 | +0.0055 | +0.0236 | +0.0150 |
| unconditional | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

---

## Table 3 — Gap dynamics

`gap_t = K_last − PM_last` on co-active bars. Positive = Kalshi premium over PM.

### 3a — |gap| statistics per fight tier

Main event = highest combined volume per event date; undercard = remainder.

| Tier | N bars | mean \|gap\| | p90 \|gap\| |
|:-----|-------:|-------------:|------------:|
| main_event | 2680 | 0.0090 | 0.0200 |
| undercard | 2189 | 0.0118 | 0.0200 |

### 3b — Gap episodes: |gap| crosses 5¢ → closes ≤ 2¢

| Tier | N episodes | N closed | N censored | median min | <30m | <2h | <6h | <24h |
|:-----|----------:|---------:|-----------:|-----------:|-----:|----:|----:|-----:|
| main_event | 1 | 1 | 0 | 30 | 100.0% | 100.0% | 100.0% | 100.0% |
| undercard | 7 | 7 | 0 | 65 | 42.9% | 85.7% | 100.0% | 100.0% |

Overall: N=8 episodes, 8 closed, 0 censored at t_end.
Median close time (closed only): 48 min

---

## Synthesis

When one venue jumps 3¢+, the other responds with a large mean aligned move on the **same bar** (+3.7¢ for K-jumps→PM, +3.5¢ for PM-jumps→K), confirming simultaneous co-movement as the dominant pattern — both venues are absorbing the same news within the same 5-minute window most of the time. However, the same-direction rates are asymmetric: 55.6% for K-jumps→PM (modestly above the ~50% null) versus 41.4% for PM-jumps→K (below the null), indicating Kalshi more often ignores or fades PM jumps than follows them. Conditional-propagation cells are too small (N=9–12 per cell) to support reliable inference, but persistent PM-jumps show a notable Kalshi counter-move at +2h (−4.75¢ aligned), tentatively consistent with Kalshi mean-reverting relative to PM rather than converging. Gap dynamics are the clearest signal: mean |gap| is only 0.9–1.2¢, gaps exceeding 5¢ are rare (N=8 over 20 fights × 72h), and all closed within 6h (median 48 min), pointing to **loose but real convergence pressure** — not tight arbitrage, but not genuine disconnection either. Overall: **simultaneous updating is the norm; delayed convergence exists but is slow and episodic; neither venue systematically leads the other at any horizon tested**.
