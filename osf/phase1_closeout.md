# Track B Phase 1 — Closeout
**Date closed:** 2026-07-14

---

## Sequence of results

### Training (collector era, Apr 2026+)
8 fight cards | 102 fights | 204 markets | 120,855 bars  
`qa/phase1_quintile_sort.md` — generated 2026-07-13, pre-registration commit 7d61b9c

| OFI variant | Q5-Q1 lag-1 (ct) | SE | t | n_cards |
|:------------|:----------------:|:--:|:-:|:-------:|
| z-OFI | −0.12 | 0.031 | −3.91 | 8 |
| volume-scaled | −0.34 | 0.054 | −6.34 | 8 |

Monotonicity (ofi_vol): decreasing across all four steps.

### Holdout (2 fight cards, sealed before training run)
Criterion: both Q5-Q1 lag-1 spreads negative.  
`qa/trackB_phase1_holdout_score.md` — scored once, 2026-07-13

| OFI variant | Q5-Q1 lag-1 (ct) | t | Sign |
|:------------|:----------------:|:-:|:----:|
| z-OFI | +0.04 | +0.33 | positive — FAIL |
| volume-scaled | −0.71 | −2.08 | negative — pass |

**Holdout verdict: NOT CONFIRMED** (criterion required both; z-OFI sign flipped, n_cards = 2)

### Confirmatory (Lychee era, Feb–Nov 2025)
Registration: `osf/trackB_confirmatory_registration.md` — committed before scoring  
26 fight cards | 368 markets | 62,149 bars (after t_end cutoff) | 483,424 trades  
`qa/trackB_confirmatory_score.md` — scored once, 2026-07-14

Criterion: volume-scaled OFI Q5-Q1 lag-1 spread **negative AND |t| ≥ 2**.

| OFI variant | Q5-Q1 lag-1 (ct) | SE | t | p | n_cards | Role |
|:------------|:----------------:|:--:|:-:|:-:|:-------:|:----:|
| volume-scaled | −1.13 | 0.179 | −6.29 | <0.0001 | 26 | PRIMARY — criterion |
| z-OFI | −0.14 | 0.107 | −1.27 | 0.2036 | 26 | secondary — reported only |

**Confirmatory verdict: CONFIRM**  
Both criterion conditions met: spread < 0 and |t| = 6.29 ≥ 2.

---

## Window-rule fidelity note

The confirmatory script applied `t_end = (close_time − 60 min).floor("5min")` per the registered specification, excluding all 5-min bars at or after that cutoff. This is the corrected rule documented in the registration; an earlier draft of the pipeline included bars up to close and was corrected before any Lychee numbers were computed.

---

## Era-magnitude observation (descriptive)

Volume-scaled OFI Q5-Q1 lag-1 spread by data era:

| Era | Period | n_cards | Spread (ct) | t |
|:----|:-------|:-------:|:-----------:|:-:|
| Collector (training) | Apr 2026+ | 8 | −0.34 | −6.34 |
| Lychee (confirmatory) | Feb–Nov 2025 | 26 | −1.13 | −6.29 |

The magnitude is approximately 3× larger in the Lychee era. t-statistics are similar. No causal account of the difference is offered here.
