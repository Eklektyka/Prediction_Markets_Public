# UFC Cross-Venue Price Discovery: Kalshi × Polymarket

Replication package for *Cross-Venue Price Discovery in UFC Prediction Markets* (2026).

---

## Overview

This repo contains the full pipeline for a cross-venue price discovery study comparing Kalshi and Polymarket on UFC fight-winner markets. The panel covers **281 fights across 35 cards (May 2025 – July 2026)**, built from two collection eras.

All paper exhibits (ex1–ex7 plus diagnostics ex5d and ex5e) are frozen from a single script run on **2026-07-17, seed=42** (commit `bb5d695`).

---

## Repository Structure

| Folder | Contents |
|:-------|:---------|
| `code/` | All pipeline scripts: data collection, crosswalk, panel build, exhibit freeze, diagnostics |
| `data/meta/` | UFC crosswalk parquet + overrides CSV |
| `paper/exhibits/` | Frozen exhibit outputs (ex1–ex7, ex5d, ex5e) as CSV and markdown |
| `paper/PAPER_BRIEF.md` | Headline numbers reference (single-vintage, bb5d695) |
| `qa/` | Full audit trail: complement-fix verification, jump inference, asymmetry robustness, side audits |
| `osf/` | Pre-registration files and exploratory log |

Raw and intermediate data files (trade-level parquets) are not included — too large for git.

---

## Data Sources

| Source | Venue | Coverage | Notes |
|:-------|:-----:|:--------:|:------|
| Polymarket data-api (taker fills) | PM | May 2025 – Jul 2026 | 2025 leg verified 1:1 against on-chain records; complement-leg duplication documented and excluded |
| Kalshi public archive + live collector | Kalshi | May 2025 – Jul 2026 | Dec 2025 – Mar 2026 gap unrecoverable |

---

## Reproducing the Exhibits

```bash
# Requires Python 3.12, pandas, numpy, scipy
py -3 code/exhibit_freeze.py        # produces paper/exhibits/ex1-ex7
py -3 code/ex5d_diagnostics.py      # bounce diagnostics
py -3 code/ex5e_large_trade.py      # large-trade split (post-hoc)
```

All three scripts are deterministic (seed=42). Runtime for exhibit_freeze.py is approximately 33 seconds.

---

## Key Results

- **CCF k=0**: ρ = +0.103 (5-min) / +0.204 (30-min), both significant; no lead-lag signal at any other horizon
- **Jump asymmetry (3¢)**: Kalshi-initiated jumps followed by PM 54.8% vs PM-initiated jumps followed by Kalshi 39.5%; diff +15.3pp [+3.4, +26.1]; dead at 5¢
- **Persistent-minus-transient contrast**: +4.4¢ K→PM, +3.4¢ PM→K at +1h, both CIs exclude zero
- **Gap closure**: main-event gaps close in ~32 min median; undercard ~118 min
- **Fragmentation ratio**: 0.81× (PM depth stable across eras; Kalshi grew ~10×)
- **OFI reversal (confirmatory)**: −1.13¢, t = −6.29, p < 0.001 (sub-tick relative to 3.45¢ round-trip fee)

---

## Citation

> *Cross-Venue Price Discovery in UFC Prediction Markets* (2026).
