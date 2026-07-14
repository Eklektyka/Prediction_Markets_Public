## Exhibit 5 — Within-Venue Order Flow (Phase 1 Summary)
**Source:** `qa/phase1_quintile_sort.md`, `qa/trackB_phase1_holdout_score.md`,
`qa/trackB_confirmatory_score.md`.  No recomputation — values frozen from QA files.
**Construction:** 5-min bars, taker_side OFI, quintile sort on lag-1 forward return (cents),
SE clustered by fight card.

### 5A — Quintile sort Q5-Q1 spread (lag-1)

| Sample | OFI variant | Q5-Q1 lag-1 (ct) | SE | t | p | n_cards |
|:-----|:----------|:---------------|:---|:---|:---|:------|
| Training (Apr 2026+, 8 cards) | z-OFI | −0.12 | 0.031 | −3.91 | 0.0001 | 8 |
| Training (Apr 2026+, 8 cards) | volume-scaled | −0.34 | 0.054 | −6.34 | <0.001 | 8 |
| Holdout (2 cards) | z-OFI | +0.04 | 0.116 | +0.33 | 0.74 | 2 |
| Holdout (2 cards) | volume-scaled | −0.71 | 0.342 | −2.08 | 0.037 | 2 |
| Confirmatory (Feb–Nov 2025, 26 cards) | volume-scaled (PRIMARY) | −1.13 | 0.179 | −6.29 | <0.001 | 26 |
| Confirmatory (Feb–Nov 2025, 26 cards) | z-OFI (secondary) | −0.14 | 0.107 | −1.27 | 0.204 | 26 |

### 5B — Verdict sequence

| Phase | Criterion | Verdict |
|:----|:--------|:------|
| Training | OFI reversal (sign validation) | FOUND — both variants negative |
| Holdout | Both Q5-Q1 spreads negative | NOT CONFIRMED — z-OFI positive |
| Confirmatory | vol-scaled < 0 AND |t| ≥ 2 | **CONFIRM** (t = −6.29) |

### 5C — Fee benchmark

| Kalshi taker fee | Round-trip at median P=0.44 | Round-trip (ct) |
|:---------------|:--------------------------|:--------------|
| 7% × P × (1-P) per side | 2 × 7% × 0.44 × 0.56 | 3.45 ct |

Confirmatory registration: `osf/trackB_confirmatory_registration.md`.
Closeout: `osf/phase1_closeout.md`.
