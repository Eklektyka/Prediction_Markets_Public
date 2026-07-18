# Track A — Macro Post-Announcement Drift: Preliminary Results

**Date:** 2026-07-13  
**Status:** Pilot — N = 6 events. Kill rule N < 20 → result is **inconclusive by construction**. No inferential conclusion drawn.

---

## 1. Data

- Source: `data/clean/trackA_event_panel.parquet`
- Usable event × market rows: 843
- Events: 97 (3 event dates × 2 series each)
- Series in panel: KXFED, KXPAYROLLS, KXCPIYOY, KXU3, KXCPICOREYOY, KXFEDDECISION

Contract selection: affected markets with expiry >72h after t0 (later-month contracts
responding to the news; contracts settled by the print dropped).

---

## 2. Return Definitions (cents)

| Return | Window | Formula |
|--------|--------|---------|
| Impact | pre → t0+30m | price_30m − pre_price |
| Drift(4h) | t0+30m → t0+4h | price_4h − price_30m |
| Drift(24h) | t0+30m → t0+24h | price_24h − price_30m |

Pre-price = last trade in [t0−6h, t0). Prices in cents (×100 from dollars).

**Descriptive statistics (cents):**

```
       impact  drift_4h  drift_24h
count  843.00    843.00     843.00
mean     0.03      0.21      -0.22
std      6.23      5.92       9.91
min    -40.00    -29.00     -78.00
25%      0.00     -1.00      -2.00
50%      0.00      0.00       0.00
75%      0.00      1.00       2.00
max     43.00     42.00      93.00
```

---

## 3. Regressions: Drift ~ Impact

Model: `Drift = α + β·Impact + ε`  
SE: cluster-robust by event where n_events ≥ 5; HC3 otherwise (noted per cell).

Interpretation: **β > 0** = underreaction (continuation); **β < 0** = overreaction (reversal); **β ≈ 0** = efficient.

| Group | Horizon | N | β | t | SE type | Events |
|-------|---------|---|---|---|---------|--------|
| Pooled | +30m→+4h | 843 | -0.1357 | -2.25 | cluster | 97 |
| Pooled | +30m→+24h | 843 | -0.1138 | -1.54 | cluster | 97 |
| CPI | +30m→+4h | 234 | -0.0416 | -0.35 | cluster | 30 |
| CPI | +30m→+24h | 234 | 0.0290 | 0.15 | cluster | 30 |
| Payrolls | +30m→+4h | 208 | -0.0670 | -1.31 | cluster | 27 |
| Payrolls | +30m→+24h | 208 | -0.0959 | -1.27 | cluster | 27 |
| FOMC | +30m→+4h | 318 | -0.2984 | -2.63 | cluster | 24 |
| FOMC | +30m→+24h | 318 | -0.2472 | -1.90 | cluster | 24 |

---

## 4. Interpretation

- **Pooled / +30m→+4h**: directional overreaction (β = -0.136, t = -2.25) — reversal signal, underpowered.
- **Pooled / +30m→+24h**: directional overreaction (β = -0.114, t = -1.54) — reversal signal, underpowered.
- **CPI / +30m→+4h**: consistent with efficiency (β ≈ 0, |t| < 1).
- **CPI / +30m→+24h**: consistent with efficiency (β ≈ 0, |t| < 1).
- **Payrolls / +30m→+4h**: directional overreaction (β = -0.067, t = -1.31) — reversal signal, underpowered.
- **Payrolls / +30m→+24h**: directional overreaction (β = -0.096, t = -1.27) — reversal signal, underpowered.
- **FOMC / +30m→+4h**: directional overreaction (β = -0.298, t = -2.63) — reversal signal, underpowered.
- **FOMC / +30m→+24h**: directional overreaction (β = -0.247, t = -1.90) — reversal signal, underpowered.

**All results are inconclusive.** With 6 events any non-zero β is consistent with noise.
Kill rule (N < 20) applies; revisit when N ≥ 20.

---

## 5. Attrition note

```
               total_usable  in_regression
event_series                              
KXCPICOREYOY            234            234
KXCPIYOY                  5              5
KXFED                   318            318
KXFEDDECISION            35             35
KXPAYROLLS              208            208
KXU3                     43             43
```

Rows drop from usable → regression only where price_30m, price_4h, or price_24h is NaN
(no trade in that window).