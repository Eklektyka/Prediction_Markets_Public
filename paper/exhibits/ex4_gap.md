## Exhibit 4 — Gap Closure
**Gap episodes:** |K_last − PM_last| crosses 5¢ → closes ≤ 2¢ (prices in [0,1]).
**ACTIVE:** both venues trade during episode.  **STALE-SIDE:** one venue has zero trades throughout.
**Tier:** main_event = top-decile combined volume (N=19).
**Bootstrap:** median CI = two-stage resample of episodes, B=1000, seed=42.

| Stratum | Type | Tier | N ep | N closed | N censored | Median min [95% CI] | <30m | <2h | <6h | Note |
|:------|:---|:---|:---|:-------|:---------|:------------------|:---|:---|:---|:---|
| ACTIVE | ACTIVE | main_event | 9 | 9 | 0 | 30 [5,90] | 44% | 89% | 100% | N=9 |
| ACTIVE | ACTIVE | undercard | 120 | 105 | 15 | 120 [85,210] | 22% | 49% | 73% | N=105 |
| STALE-SIDE | STALE-SIDE | all | 7 | 6 | 1 | 10 [5,495] | 67% | 83% | 83% | N=6 |
