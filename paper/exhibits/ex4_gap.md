## Exhibit 4 — Gap Closure
**Gap episodes:** |K_last − PM_last| crosses 5¢ → closes ≤ 2¢ (prices in [0,1]).
**ACTIVE:** both venues trade during episode.  **STALE-SIDE:** one venue has zero trades throughout.
**Tier:** main_event = top-decile combined volume (N=32).
**Bootstrap:** median CI = two-stage resample of episodes, B=1000, seed=42.

| Stratum | Type | Tier | N ep | N closed | N censored | Median min [95% CI] | <30m | <2h | <6h | Note |
|:------|:---|:---|:---|:-------|:---------|:------------------|:---|:---|:---|:---|
| ACTIVE pooled | ACTIVE | main_event | 12 | 12 | 0 | 32 [10,80] | 50% | 83% | 100% | N=12 |
| ACTIVE pooled | ACTIVE | undercard | 144 | 126 | 18 | 118 [80,170] | 25% | 50% | 71% | N=126 |
| STALE-SIDE pooled | STALE-SIDE | all | 11 | 10 | 1 | 10 [5,25] | 80% | 90% | 90% | N=10 |
| ACTIVE 2025_lychee | ACTIVE | main_event | 12 | 12 | 0 | 32 [10,80] | 50% | 83% | 100% | N=12 |
| ACTIVE 2025_lychee | ACTIVE | undercard | 129 | 114 | 15 | 98 [75,165] | 26% | 53% | 75% | N=114 |
| ACTIVE 2026_collector | ACTIVE | main_event | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a |
| ACTIVE 2026_collector | ACTIVE | undercard | 15 | 12 | 3 | 375 [92,1115] | 17% | 25% | 42% | N=12 |
