# Track B Confirmatory Score
**Generated:** 2026-07-14 12:13 UTC
**Registration:** `osf/trackB_confirmatory_registration.md`
**ONE LOOK — do not re-run or modify after first execution.**

---

## Verdict

# CONFIRM

| Metric | Value |
|:-------|------:|
| Volume-scaled OFI Q5-Q1 spread (lag-1, cents) | **−1.1265** |
| t-statistic (SE clustered by fight card) | −6.29 |
| p-value (two-sided, normal approx.) | < 0.0001 |
| n_cards | 26 |
| Confirmation criterion | spread < 0 AND \|t\| ≥ 2 |
| **Verdict** | **CONFIRM** |

**Secondary (reported, not criterion):**
- z-OFI Q5-Q1 spread (lag-1): −0.1356 ct  (t=−1.27)

> **Unit-scaling note (post-hoc correction, verdict unchanged):**
> `phase1_quintile_sort.py` stores `yes_price` in dollars (0-1) and multiplies `dp_1` by 100 to convert to cents.
> Lychee `yes_price` is already in cents (0-100), so `dp_1` is in cents and the ×100 is applied twice.
> Raw output spread values were 100× too large (−112.65 ct raw → −1.1265 ct corrected; −13.56 ct raw → −0.1356 ct corrected).
> The t-statistics (−6.29 and −1.27) are scale-invariant and correct as reported.
> The confirmation criterion depends only on sign (negative ✓) and |t| ≥ 2 (6.29 ✓). **Verdict: CONFIRM — unchanged.**

---

## Sample

| Statistic | Value |
|:----------|------:|
| Trades (KXUFCFIGHT, Feb–Nov 2025, price 5–95¢, ≥50 trades, pre-t_end) | 483,424 |
| Markets (tickers) after t_end filter | 368 |
| 5-min bars after t_end filter | 62,149 |
| Fight cards | 26 |
| Bars with valid ofi_vol | 62,149 |
| t_end rule | (close_time − 60 min).floor("5min") |

---

## Volume-scaled OFI Quintile Sort (PRIMARY)

| Quintile | Mean ofi_vol | Mean dp_lag1 (cents) |
|:--------:|:------------:|:--------------------:|
| Q1 | -0.0502 | +0.3880 |
| Q2 | 0.0044 | -0.0832 |
| Q3 | 0.0141 | -0.0869 |
| Q4 | 0.0456 | -0.0801 |
| Q5 | 0.3934 | -0.2875 |

*(dp_lag1 corrected: raw values ÷ 100 to convert from script artifact to actual cents)*

**Q5-Q1 spread:** −1.1265 ct
**SE (card-clustered):** 0.1791
**t:** −6.29
**p:** < 0.0001
**n_cards:** 26
**n_bars:** 62,119

---

## z-scored OFI Quintile Sort (SECONDARY — reported, not criterion)

| Quintile | Mean ofi_z | Mean dp_lag1 (cents) |
|:--------:|:----------:|:--------------------:|
| Q1 | -0.5067 | +0.0455 |
| Q2 | -0.2337 | -0.0265 |
| Q3 | -0.1622 | -0.0313 |
| Q4 | -0.0695 | -0.0635 |
| Q5 | 0.9711 | -0.0741 |

*(dp_lag1 corrected: raw values ÷ 100)*

**Q5-Q1 spread:** −0.1356 ct
**SE (card-clustered):** 0.1067
**t:** −1.27
**p:** 0.2036
**n_cards:** 26

---

## Construction Rules

Identical to `code/phase1_quintile_sort.py` except:
- **Data:** Lychee parquet files (`C:/Kalshi_data/lychee/extracted/data/kalshi/trades/`)
- **yes_price:** already in CENTS (0-100); filter applied as `[5, 95]`
- **MIN_TRADES:** 50 (registration specifies 50; Phase 1 used 100)
- **t_end:** `(close_time - 60min).floor("5min")` — bars after t_end excluded
- **Lag scored:** lag-1 only (per registration)
- **OFI sign:** `taker_side='yes'` → +count (positive); `taker_side='no'` → -count
- **vol_6h:** rolling 6h sum of total_count per ticker (window="360min")
- **ofi_vol:** `ofi / vol_6h`; `ofi_z`: within-market z-score (full window)
- **SE clustering:** per-card Q5-Q1 spreads, `std(ddof=1) / sqrt(n_cards)`
