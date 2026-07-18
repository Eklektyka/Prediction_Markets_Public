# Track B Phase 1 — Holdout Score

**One-shot scoring per amended registration (commit 51711bc, 2026-07-13).**  
Confirmation criterion: both Q5-Q1 lag-1 spreads negative.  
No other holdout statistics computed.

Holdout: 15 fights | 25 markets | 37,683 bars

| OFI variant | Q5-Q1 lag-1 (ct) | SE | t | p | n_cards | Sign |
|-------------|------------------|----|---|---|---------|------|
| z-OFI           | +0.0386 | 0.1157 | +0.33 | 0.7389 | 2 | >0 FAIL |
| volume-scaled   | -0.7126 | 0.3419 | -2.08 | 0.0371 | 2 | <0 checkmark |

## Verdict: NOT CONFIRMED

z-OFI spread positive, volume-scaled spread negative. Criterion not met.
