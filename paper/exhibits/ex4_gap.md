## Exhibit 4 — Gap Closure
**Gap episodes:** |K_last − PM_last| crosses 5¢ → closes ≤ 2¢ (prices in [0,1]).
**ACTIVE:** both venues trade during episode.  **STALE-SIDE:** one venue has zero trades throughout.
**Tier:** main_event = top-decile combined volume (N=19).
**Bootstrap:** median CI = two-stage resample of episodes, B=1000, seed=42.

| Stratum | Type | Tier | N ep | N closed | N censored | Median min [95% CI] | <30m | <2h | <6h | Note |
|:------|:---|:---|:---|:-------|:---------|:------------------|:---|:---|:---|:---|
| ACTIVE | ACTIVE | main_event | 9 | 9 | 0 | 30 [5,90] | 44% | 89% | 100% | N=9 |
| ACTIVE | ACTIVE | undercard | 132 | 117 | 15 | 100 [75,165] | 26% | 52% | 75% | N=117 |
| STALE-SIDE | STALE-SIDE | all | 8 | 7 | 1 | 10 [5,40] | 71% | 86% | 86% | N=7 |
