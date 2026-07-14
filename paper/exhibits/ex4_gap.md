## Exhibit 4 — Gap Closure
**Gap episodes:** |K_last − PM_last| crosses 5¢ → closes ≤ 2¢ (prices in [0,1]).
**ACTIVE:** both venues trade during episode.  **STALE-SIDE:** one venue has zero trades throughout.
**Tier:** main_event = top-decile combined volume (N=32).
**Bootstrap:** median CI = two-stage resample of episodes, B=1000, seed=42.

| Stratum | Type | Tier | N ep | N closed | N censored | Median min [95% CI] | <30m | <2h | <6h | Note |
|:------|:---|:---|:---|:-------|:---------|:------------------|:---|:---|:---|:---|
| ACTIVE pooled | ACTIVE | main_event | 12 | 12 | 0 | 38 [12,80] | 42% | 83% | 100% | N=12 |
| ACTIVE pooled | ACTIVE | undercard | 145 | 127 | 18 | 120 [85,195] | 24% | 49% | 71% | N=127 |
| STALE-SIDE pooled | STALE-SIDE | all | 9 | 8 | 1 | 10 [5,40] | 75% | 88% | 88% | N=8 |
| ACTIVE 2025_lychee | ACTIVE | main_event | 12 | 12 | 0 | 38 [12,80] | 42% | 83% | 100% | N=12 |
| ACTIVE 2025_lychee | ACTIVE | undercard | 130 | 115 | 15 | 115 [75,195] | 25% | 51% | 74% | N=115 |
| ACTIVE 2026_collector | ACTIVE | main_event | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a |
| ACTIVE 2026_collector | ACTIVE | undercard | 15 | 12 | 3 | 375 [92,1115] | 17% | 25% | 42% | N=12 |

*2026_collector rows use global Polymarket CLOB only (data-api.polymarket.com); US QCX flow excluded. 2026 PM ~3x thinner per fight (median 154 vs 422 trades); longer median closure time (375 min vs 115 min) consistent with thinner PM liquidity. See Ex6.*
