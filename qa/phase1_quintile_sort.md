# Track B Phase 1 -- OFI Quintile Sort (standardised variants)

Generated: 2026-07-13  
Pre-registration: OSF commit 7d61b9c. `data/holdout/` not accessed.  
OFI sign convention verified correct: `taker_side=yes` -> +count (see `qa/signing_check.md`).

**Sample:** 120,855 bars | 204 markets | 102 fights | 8 fight cards

Markets dropped (ofi_sd = 0): 0  
Bars with valid ofi_z: 120,855  
Bars with valid ofi_vol: 120,855

## Sign Validation and OLS (z-scored OFI)

Contemporaneous expected **positive** (net yes-buying lifts same-bar price).  Lagged expected **negative** (Phase 1 reversal).

Pooled Pearson r(ofi_z, dp_contemp) = **-0.090767** (NEGATIVE -- FLAG)  
Pooled Pearson r(ofi_z, dp_lag1)    = +0.020696  

### OLS: dprice ~ ofi_z  (ticker FE; SE clustered by fight)

| Horizon | Beta ($/sd) | SE | t | p | 95% CI | n | G |
|---------|-------------|----|----|---|--------|---|---|
| contemporaneous [sign check] | -1.8111e-03 | 4.4393e-04 | -4.08 | 0.0000 | [-2.6812e-03, -9.4098e-04] | 120,651 | 102 |
| lag 1 [Phase 1 reversal] | +4.1599e-04 | 1.6332e-04 | +2.55 | 0.0109 | [+9.5871e-05, +7.3610e-04] | 120,651 | 102 |
| lag 2 [skip-one bar] | -1.9782e-04 | 1.9704e-04 | -1.00 | 0.3154 | [-5.8403e-04, +1.8838e-04] | 120,447 | 102 |

**WARNING: contemporaneous beta is NOT positive. If confirmed, Phase 1 reversal and continuation labels are flipped. Stop and investigate before re-running anything.**

## Quintile Sorts

Bars pooled across all markets. Quintile bins computed on the pooled distribution of the normalised OFI variant.  
Returns in **cents** (dollar price change x 100).  
Q5-Q1 spread SE clustered by fight card (event date).  
Strictly lagged: OFI in bar t predicts return from close(t) to close(t+1) for lag 1, and close(t+1) to close(t+2) for lag 2 (no shared trades).


### z-scored OFI (within-market standardised)

| quintile | mean OFI | dp_lag1 (ct) | dp_lag2 skip-one (ct) |
|----------|----------|--------------|-----------------------|
| Q1 | -0.2061 | +0.0486 | -0.0064 |
| Q2 | -0.1245 | -0.0079 | -0.0031 |
| Q3 | -0.0970 | -0.0131 | -0.0022 |
| Q4 | -0.0716 | -0.0082 | +0.0007 |
| Q5 | 0.4997 | -0.0312 | -0.0033 |

**lag 1** Q5-Q1 spread: -0.1215 ct | SE (card-clustered): 0.0311 | t: -3.91 | p: 0.0001 | n_cards: 8 | monotonicity: non-monotone (1 up / 3 down steps)  
**lag 2 skip-one** Q5-Q1 spread: +0.0328 ct | SE (card-clustered): 0.0383 | t: +0.86 | p: 0.3920 | n_cards: 8 | monotonicity: non-monotone (3 up / 1 down steps)  

### volume-scaled OFI (OFI / rolling 6-hour volume)

| quintile | mean OFI | dp_lag1 (ct) | dp_lag2 skip-one (ct) |
|----------|----------|--------------|-----------------------|
| Q1 | -0.0338 | +0.2769 | +0.0222 |
| Q2 | 0.0047 | -0.0558 | -0.0136 |
| Q3 | 0.0130 | -0.0667 | -0.0034 |
| Q4 | 0.0339 | -0.0752 | +0.0111 |
| Q5 | 0.2466 | -0.0896 | -0.0305 |

**lag 1** Q5-Q1 spread: -0.3417 ct | SE (card-clustered): 0.0539 | t: -6.34 | p: 0.0000 | n_cards: 8 | monotonicity: decreasing  
**lag 2 skip-one** Q5-Q1 spread: -0.0480 ct | SE (card-clustered): 0.0211 | t: -2.28 | p: 0.0228 | n_cards: 8 | monotonicity: non-monotone (2 up / 2 down steps)  

## Economic Interpretation

**Minimum tick:** 1 cent (verified from data: p10-p75 of non-zero |dprice| = 1.00 ct).  

**Q5-Q1 spread (z-OFI, lag 1):** -0.1215 ct  
Expected sign: negative (Q1 outperforms Q5 = reversal, consistent with Phase 1).

**Kalshi taker fee estimate**  
Schedule: fee = 0.07 x P x (1-P) per contract per side  
*(Verify at help.kalshi.com/en/articles/fee-schedule before relying on this.)*  
Median yes_price in training set: P = 0.440  
Fee per side at median P: **1.725 ct/contract**  
Round-trip (buy + sell or sell + buy): **3.450 ct/contract**

|Q5-Q1| = 0.1215 ct  
1-cent tick: 0.1215 ct (sub-tick)  
Round-trip fee: 3.450 ct  
Spread / fee ratio: 0.0352x

**Verdict:** **NOT economically meaningful.** The Q5-Q1 spread is sub-tick (0.1215 ct < 1 ct minimum price increment) and is 28x smaller than the round-trip fee burden (3.450 ct). The signal is statistically real (Phase 1: perm_p = 0.0095) but is not tradeable: the expected edge cannot survive execution costs or the discrete price grid.


## Contemporaneous Sign Check (same-bar dp_contemp on same-bar z-OFI)

Same-bar price change sorted by same-bar z-scored OFI (pooled, no FE).  
Expected: **monotone increasing, Q5-Q1 strongly positive**  
(net yes-buying in bar t lifts close(t) above close(t-1)).

| quintile | mean z-OFI | dp_contemp (ct) | n_bars |
|----------|-----------|-----------------|--------|
| Q1 | -0.2061 | -0.0599 | 24,131 |
| Q2 | -0.1245 | -0.0112 | 24,130 |
| Q3 | -0.0970 | +0.0166 | 24,130 |
| Q4 | -0.0716 | +0.0130 | 24,130 |
| Q5 | +0.5002 | +0.0295 | 24,130 |

**Q5-Q1 spread: +0.0954 ct** | SE (card-clustered): 0.0471 | t: +2.03 | p: 0.0428 | n_cards: 8 | monotonicity: non-monotone (3 up / 1 down steps)

