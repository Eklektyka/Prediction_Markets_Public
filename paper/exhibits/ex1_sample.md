## Exhibit 1 — Sample & Descriptives
**Source:** `data/clean/phase2_full_panel.parquet`
**Generated:** code/exhibit_freeze.py

### 1A — Overall sample

| Metric | Value |
|:-----|:----|
| Fights in panel (raw) | 182 |
| Fights analyzed (after pm_flip exclusion) | 178 |
| pm_flip excluded fights | 20250823_MUDBOR; 20250906_HARFER; 20250906_SAIRUF; 20251122_SPIGAZ |
| Fight cards (event dates) | 26 |
| Date range | 2025-05-10 — 2025-11-22 |
| Total 5-min bars | 106,055 |
| Co-active bars (both venues) | 11,448  (10.8%) |
| Kalshi trades | 110,431 |
| Kalshi volume (contracts) | 23,265,014 |
| PM trades | 130,654 |
| PM notional (USDC, ÷1e6 from raw Polygon units) | 38,119,263 |

### 1B — Co-active coverage distribution (share of 5-min bars where both venues traded)

| Percentile | Both% (share of 5-min bars co-active) |
|:---------|:------------------------------------|
| p10 | 2.0% |
| p25 | 3.5% |
| p50 (median) | 5.5% |
| p75 | 10.5% |
| p90 | 18.2% |

Fights in 5-min stratum (both% ≥ 25%): **10**

### 1C — Fights by tier

| Tier | N fights | Definition |
|:---|:-------|:---------|
| main_event | 19 | Top 10% by combined K+PM volume (>= 2,444,123 contracts+USDC) |
| undercard | 159 | Remainder |

### 1D — Level gap K − PM (co-active bars, prices in [0,1])

| Stratum | N bars | Mean gap (K−PM) | Median gap (K−PM) | Mean |gap| |
|:------|:-----|:--------------|:----------------|:---------|
| All co-active bars | 11,448 | +0.0055 | +0.0100 | 0.0129 |
| main_event | 4,739 | +0.0045 | +0.0000 | 0.0103 |
| undercard | 6,709 | +0.0062 | +0.0100 | 0.0148 |

*Gap = K_last − PM_last on co-active bars (both_traded=True, both prices non-NaN). Positive = Kalshi above PM. Prices in [0, 1] scale (probability); 0.01 = 1 percentage point.*
