# Track A — Macro Post-Announcement Drift: Preliminary Results

**Date:** 2026-07-13  
**Status:** Pilot — N = 6 events. Kill rule N < 20 → result is **inconclusive by construction**. No inferential conclusion drawn.

---

## 1. Data

- Source: `data/clean/trackA_event_panel.parquet`
- Usable event × market rows: 199
- Events: 6 (3 event dates × 2 series each)
- Series in panel: KXPAYROLLS, KXCPICOREYOY, KXFED

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
count  199.00    199.00     199.00
mean     0.17      0.31      -0.02
std      4.57      5.51      12.79
min    -33.00    -29.00     -37.00
25%      0.00      0.00      -2.00
50%      0.00      0.00       0.00
75%      0.00      0.00       2.00
max     42.00     31.00      93.00
```

---

## 3. Regressions: Drift ~ Impact

Model: `Drift = α + β·Impact + ε`  
SE: cluster-robust by event where n_events ≥ 5; HC3 otherwise (noted per cell).

Interpretation: **β > 0** = underreaction (continuation); **β < 0** = overreaction (reversal); **β ≈ 0** = efficient.

| Group | Horizon | N | β | t | SE type | Events |
|-------|---------|---|---|---|---------|--------|
| Pooled | +30m→+4h | 199 | 0.2765 | 3.30 | cluster | 6 |
| Pooled | +30m→+24h | 199 | 0.1996 | 1.22 | cluster | 6 |
| CPI | +30m→+4h | 74 | 0.3266 | 0.94 | HC3 | 2 |
| CPI | +30m→+24h | 74 | 0.3922 | 1.28 | HC3 | 2 |
| Payrolls | +30m→+4h | 73 | 0.1027 | 1.75 | HC3 | 3 |
| Payrolls | +30m→+24h | 73 | -0.0991 | -0.70 | HC3 | 3 |
| FOMC | +30m→+4h | 52 | 0.7181 | 2.95 | HC3 | 1 |
| FOMC | +30m→+24h | 52 | 0.8975 | 2.46 | HC3 | 1 |

---

## 4. Interpretation

- **Pooled / +30m→+4h**: directional underreaction (β = 0.277, t = 3.30) — continuation signal, underpowered.
- **Pooled / +30m→+24h**: directional underreaction (β = 0.200, t = 1.22) — continuation signal, underpowered.
- **CPI / +30m→+4h**: β = 0.327, t = 0.94 — inconclusive.
- **CPI / +30m→+24h**: directional underreaction (β = 0.392, t = 1.28) — continuation signal, underpowered.
- **Payrolls / +30m→+4h**: directional underreaction (β = 0.103, t = 1.75) — continuation signal, underpowered.
- **Payrolls / +30m→+24h**: β = -0.099, t = -0.70 — inconclusive.
- **FOMC / +30m→+4h**: directional underreaction (β = 0.718, t = 2.95) — continuation signal, underpowered.
- **FOMC / +30m→+24h**: directional underreaction (β = 0.897, t = 2.46) — continuation signal, underpowered.

**All results are inconclusive.** With 6 events any non-zero β is consistent with noise.
Kill rule (N < 20) applies; revisit when N ≥ 20.

---

## 5. Attrition note

```
              total_usable  in_regression
event_series                             
KXCPICOREYOY            74             74
KXFED                   52             52
KXPAYROLLS              73             73
```

Rows drop from usable → regression only where price_30m, price_4h, or price_24h is NaN
(no trade in that window).