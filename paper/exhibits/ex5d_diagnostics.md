# Exhibit 5D — OFI Bounce Diagnostics (Skip-One, Liquidity Split, Roll Bound)
**Generated:** 2026-07-18 17:11 UTC
**Script:** `code/ex5d_diagnostics.py`
**Panel:** 26 fight cards, Feb–Nov 2025, 5-min bars, [5,95]¢ price filter, card-clustered SE.
**Prior vintage commit:** bb5d695

---

## (a) Vintage Check and Checksum Reproduction

### Vintage Check

**Command:** `git diff bb5d695 -- code/trackB_phase1_orderflow.py code/phase1_quintile_sort.py code/score_trackB_holdout.py code/trackB_confirmatory_score.py data/interim/lychee_macro_trades.parquet`

**Result:** No diff. No relevant OFI pipeline file changed since bb5d695. Proceeding to checksum.

### Checksum: Confirmatory Panel (ex5 values)

| Metric | Reproduced | Expected | Verdict |
|:-------|----------:|--------:|:--------|
| vol-OFI Q5-Q1 lag-1 (ct) | -1.1265 | −1.1265 | PASS |
| t-statistic (vol-OFI) | -6.29 | −6.29 | PASS |
| z-OFI Q5-Q1 lag-1 (ct) | -0.1356 | −0.1356 | PASS |
| t-statistic (z-OFI) | -1.27 | −1.27 | PASS |
| n_cards | 26 | 26 | — |
| n_bars | 62,119 | 62,119 | — |

**Checksum status: PASS** — proceeding to diagnostics.

#### Volume-scaled OFI Quintile Sort (lag-1)

| Quintile | Mean ofi_vol | Mean dp_lag1 (cents) |
|:--------:|:------------:|:--------------------:|
| Q1 | -0.0502 | +0.3880 |
| Q2 | 0.0044 | -0.0832 |
| Q3 | 0.0141 | -0.0869 |
| Q4 | 0.0456 | -0.0801 |
| Q5 | 0.3934 | -0.2875 |

#### z-OFI Quintile Sort (lag-1)

| Quintile | Mean ofi_z | Mean dp_lag1 (cents) |
|:--------:|:----------:|:--------------------:|
| Q1 | -0.5067 | +0.0455 |
| Q2 | -0.2337 | -0.0265 |
| Q3 | -0.1622 | -0.0313 |
| Q4 | -0.0695 | -0.0635 |
| Q5 | 0.9711 | -0.0741 |


---

## (b) Fresh Diagnostic Values

### D.2 Skip-One (Lag-2 Quintile Spreads)

Computed BEFORE reading prior vintage values.

| OFI Variant | Q5-Q1 lag-2 (ct) | SE | t | p | n_cards |
|:-----------|:----------------:|:---:|:---:|:---:|:------:|
| z-OFI | +0.0161 | 0.0336 | +0.48 | 0.6316 | 26 |
| volume-scaled | -0.1530 | 0.0505 | -3.03 | 0.0025 | 26 |

### D.3 Liquidity Split

Computed BEFORE reading prior vintage values.

**Sample split:** median market total trades = 162
Thin markets: 184 | Thick markets: 184

**Regression spec:** dp_1 (raw price change, cents scale) ~ intercept + ofi (signed contract count); card-clustered sandwich SE.

| Subsample | Coef (dp/contract) | SE | t | p | n_bars |
|:---------|:-----------------:|:---:|:---:|:---:|:-----:|
| Thin (below-median trades) | 3.2766e-05 | 1.7681e-05 | +1.85 | 0.0639 | 10,123 |
| Thick (above-median trades) | -3.1457e-06 | 1.9742e-06 | -1.59 | 0.1111 | 51,996 |
| Thick, multi-trade bars only | -3.7998e-06 | 1.9981e-06 | -1.90 | 0.0572 | 28,231 |

**Single-trade bars:** coef=-3.8606e-05  t=-2.22  p=0.0266  n=30,827
**Multi-trade bars:** coef=-3.9234e-06  t=-1.95  p=0.0516  n=31,292
**Depth ratio (single/multi):** 9.84×

### D.4 Roll Bound

Computed BEFORE reading prior vintage values.

**Roll half-spread:** Per-market first-order autocovariance of transaction price changes.
Markets with non-negative autocovariance: half-spread = 0.

| Statistic | Value |
|:----------|------:|
| Markets used in Roll calculation | 368 |
| Markets with negative autocov (s > 0) | 310 |
| Markets with zero half-spread (autocov ≥ 0) | 58 |
| Median half-spread (across markets) | 0.3916 ct |
| Median \|ofi\| per bar | 72.00 contracts |
| Bounce-implied flow coef (2s / med\|ofi\|) | 1.0876e-02 |
| Measured flow coef (pooled OLS, same as D.3) | -2.7512e-06 |
| Ratio (implied / \|measured\|) | 3953.3× |
| Equiv. imbalance (2s / \|coef\|) | 284640 contracts |
| Zero-price-change bars | 48,353 / 62,119 = 77.8% |

---

## (c) Side-by-Side Comparison: Prior vs Fresh

### D.2 Skip-One

| Cell | Prior (bb5d695) | Fresh | Verdict |
|:-----|:---------------:|:-----:|:-------:|
| z-OFI Q5-Q1 lag-2 (ct) | +0.033 (n.s.) | +0.0161 (p=0.632) | DRIFT (1.69e-02) |
| vol-OFI Q5-Q1 lag-2 (ct) | −0.048 (p=0.023) | -0.1530 (p=0.002) | DRIFT (1.05e-01) |

### D.3 Liquidity Split

| Cell | Prior | Fresh | Verdict |
|:-----|:-----:|:-----:|:-------:|
| Thin coef (dp/contract) | 7.6e-8 | 3.2766e-05 | DRIFT (43013.6%) |
| Thin p-value | 0.514 | 0.064 | DRIFT (4.50e-01) |
| Thick coef (dp/contract) | −5.67e-9 | -3.1457e-06 | DRIFT (55380.5%) |
| Thick p-value | 0.022 | 0.111 | DRIFT (8.91e-02) |
| Thick multi-trade coef | −5.75e-9 | -3.7998e-06 | DRIFT (65983.6%) |
| Thick multi-trade p | 0.021 | 0.057 | DRIFT (3.62e-02) |
| Depth ratio (single/multi) | ~290× | 9.8× | DRIFT (2.80e+02) |

### D.4 Roll Bound

| Cell | Prior | Fresh | Verdict |
|:-----|:-----:|:-----:|:-------:|
| Median half-spread (ct) | 0.34 | 0.3916 | DRIFT (5.16e-02) |
| Implied coef (~at med flow) | ~−6e-5 | 1.0876e-02 | DRIFT (18227.5%) |
| Measured coef (pooled OLS) | −5.2e-9 | -2.7512e-06 | DRIFT (52808.1%) |
| Ratio (implied/\|measured\|) | ~12,000× | 3953× | DRIFT (8.05e+03) |
| Equiv. imbalance (contracts) | 658,515 | 284640 | DRIFT (3.74e+05) |
| Zero-price-change bars | 79.7% | 77.8% | MATCH |

---

## (d) Spec Descriptions (for Appendix D)

**D.2 Skip-One.** Quintile sort on lag-2 (skip-one bar) forward return for both OFI variants (z-OFI and volume-scaled), on the same confirmatory panel (26 fight cards, Feb–Nov 2025, 5-min bars, [5,95]¢ filter). Q5-Q1 spread and card-clustered t-statistic are computed identically to the ex5 primary analysis, with dp_2 (return from close(t+1) to close(t+2)) as the outcome. If the reversal is driven by bid-ask bounce, it should attenuate at lag-2; if persistence or delayed information processing drives it, the lag-2 spread should be nonzero.

**D.3 Liquidity Split.** Markets are split at the median total-trade count (summed over all bars in the panel). Within each half, OLS regresses dp_1 (lag-1 price change in raw cents) on signed flow (ofi, contract-count units), with an intercept, SE clustered by fight card. The coefficient is also estimated on the thick half restricted to multi-trade bars (n > 1), and the single-trade vs multi-trade bar coefficient ratio is reported. Under a microstructure bounce, thinner markets with noisier prices and higher effective spreads should show a larger reversal coefficient; under an information story, the split should be irrelevant or opposite.

**D.4 Roll Bound.** Per-market effective half-spread is estimated via the Roll (1984) bound: s = sqrt(max(−Cov(dp_t, dp_{t-1}), 0)), where dp is the first difference of last_price within each market and covariance is computed with ddof=1; markets with non-negative autocovariance receive s = 0. The median half-spread across all markets is reported. The bounce-implied flow coefficient is 2s / median|ofi|, i.e., the price impact (in spread units) per median bar's signed flow. The measured flow coefficient comes from the pooled OLS in D.3. Their ratio and the equivalent imbalance (contracts needed to generate a full-spread move) quantify how much of the observed reversal is consistent with mechanical bounce versus genuine information.

---

## Documented Ambiguities (no prior code found for D.3 and D.4)

| ID | Ambiguity | Choice Made |
|:---|:----------|:------------|
| D.3-A | Market size proxy | Total trades = sum of bar-level n per ticker |
| D.3-B | Regressand and units | dp_1 in raw price units (cents 0-100 scale); ofi in raw contracts |
| D.3-C | SE clustering | Card-clustered (same as ex5) |
| D.3-D | Multi-trade bars | n > 1 (strictly more than one trade per bar) |
| D.3-F | Depth ratio | Single-trade coef / multi-trade coef |
| D.4-A | Negative autocov treatment | half-spread = 0 (per Roll's bound) |
| D.4-B | Autocovariance estimator | Sample covariance, ddof=1, consecutive dp pairs |
| D.4-D | Implied coefficient formula | 2*s / median(|ofi|) across all bars |
| D.4-F | Equivalent imbalance | 2*s / |measured_coef| |
