## Exhibit 7 — Asymmetry Robustness (Supplementary)
**Source:** `data/clean/phase2_full_panel.parquet` (281 fights, HARFER excluded)
**Generated:** qa/phase2_asymmetry_robustness_v2.md (no recomputation — numbers frozen from QA run 2026-07-14 15:02 UTC)
**Bootstrap:** two-stage, B=500, seed=42, fight-level clustering (resample fight rows)
**Stratum:** 30-min co-active bars, >=3c and >=5c jump thresholds
**Test:** K->PM same-dir rate minus PM->K same-dir rate; CI excludes 0 = survives

### Panel A — Survivors table: does the asymmetry survive fight-clustered bootstrap?

| era | thresh | K->PM N | K->PM same | PM->K N | PM->K same | diff | 95% CI | p | survives clustering? |
|:----|:------:|--------:|-----------:|--------:|-----------:|-----:|:------:|--:|:-------------------:|
| pooled | 3c | 219 | 55.7% | 237 | 43.0% | +12.7pp | [+2.6, +23.1] | 0.012 | **YES** |
| pooled | 5c | 110 | 53.6% | 81 | 55.6% | -1.9pp | [-15.4, +13.0] | 0.804 | no |
| 2025_lychee | 3c | 183 | 53.0% | 197 | 41.6% | +11.4pp | [+0.4, +21.6] | 0.044 | **YES** |
| 2025_lychee | 5c | 100 | 52.0% | 64 | 56.2% | -4.2pp | [-20.4, +11.4] | 0.624 | no |
| 2026_collector | 3c | 36 | 69.4% | 40 | 50.0% | +19.4pp | [-2.3, +37.4] | 0.076 | **no** (underpowered N=36) |
| 2026_collector | 5c | 10 | 70.0% | 17 | 52.9% | +17.1pp | [-22.2, +49.0] | 0.340 | no (N=10) |

### Panel B — Verdicts per era

**Pooled:** 3c survives (p=0.012, CI excludes 0). K->PM 55.7% vs PM->K 43.0%, +12.7pp. 5c reverses sign
(-1.9pp, p=0.804) — asymmetry is a small-jump phenomenon only.

**2025_lychee:** 3c survives (p=0.044, CI [+0.4, +21.6] just above 0). Replicates pooled finding within era.
5c does not survive (-4.2pp, p=0.624).

**2026_collector:** 3c does NOT survive fight-clustered bootstrap (p=0.076, CI includes 0). Point estimate is
large (+19.4pp, 69.4% vs 50.0%) but N=36 K->PM jumps across 91 fights is insufficient for clustering to
resolve. Two additional caveats: (a) 2026 PM source is global CLOB only — US QCX flow absent (see Ex6);
(b) thin 2026 PM books (median 154 vs 422 trades/fight) increase PM price staleness at the moment of a
Kalshi jump, which can mechanically inflate the K->PM same-direction rate. Direction is consistent with
pooled finding; verdict deferred pending more 2026 events.

### Panel C — Size-conditioning summary

| era | 3c survives AND 5c survives | interpretation |
|:----|:---------------------------|:--------------|
| pooled | YES / no | Asymmetry at small jumps only; large jumps show no lead |
| 2025_lychee | YES / no | Same pattern within era |
| 2026_collector | no / no | Underpowered; directionally consistent but inconclusive |

**Conclusion:** The K->PM jump-response asymmetry (+12.7pp at >=3c, p=0.012) is established in the pooled
sample and replicates within 2025_lychee (p=0.044). It does not extend to larger (>=5c) jumps, suggesting
the lead reflects high-frequency, small-magnitude price updating rather than large information events.
The 2026_collector era cannot confirm or deny this result with current N.
