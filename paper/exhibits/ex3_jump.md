## Exhibit 3 — Jump Anatomy (30-min stratum, 281 fights)
**Jump:** |ret| >= threshold on co-active 30-min bars.
**B's response:** B's return on same bar, signed by A's direction.
**Bootstrap:** B=1000, seed=42, two-stage by fight.

### Panel A — Three-bucket decomposition (>= 3c jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥3¢) | 219 | 122 (55.7%) | 38 (17.4%) | 59 (26.9%) |
| PM→K (≥3¢) | 237 | 102 (43.0%) | 102 (43.0%) | 33 (13.9%) |
| K→PM same-rate minus PM→K same-rate | — | +12.7pp  95% CI [-2.4, +21.6]pp | — | — |

### Panel B — Three-bucket decomposition (>= 5c jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥5¢) | 110 | 59 (53.6%) | 20 (18.2%) | 31 (28.2%) |
| PM→K (≥5¢) | 81 | 45 (55.6%) | 26 (32.1%) | 10 (12.3%) |
| K→PM same-rate minus PM→K same-rate | — | -1.9pp  95% CI [-24.4, +12.0]pp | — | — |

### Panel C — Persistent vs transient propagation (>= 3c, 30-min bars)
PERSISTENT = A's price still >= 50% of jump after 60 min (2 bars). Values = B's aligned cumulative return. CIs two-stage bootstrap by fight.

| Direction | Class | N | same (mean [95% CI]) | +30m (mean [95% CI]) | +1h (mean [95% CI]) | +2h (mean [95% CI]) |
|:--------|:----|:---|:-------------------|:-------------------|:------------------|:------------------|
| K→PM | PERSISTENT | 129 | +0.0215 [+0.0067,+0.0319] | +0.0139 [+0.0029,+0.0184] | +0.0222 [+0.0060,+0.0279] | +0.0172 [+0.0003,+0.0256] |
| K→PM | TRANSIENT | 59 | +0.0127 [-0.0011,+0.0333] | -0.0229 [-0.1009,-0.0013] | -0.0298 [-0.0993,-0.0058] | -0.0127 [-0.0253,+0.0011] |
| PM→K | PERSISTENT | 141 | +0.0251 [+0.0120,+0.0501] | +0.0067 [+0.0003,+0.0122] | +0.0136 [+0.0038,+0.0173] | +0.0176 [+0.0024,+0.0252] |
| PM→K | TRANSIENT | 75 | +0.0039 [-0.0015,+0.0101] | -0.0215 [-0.0725,+0.0012] | -0.0268 [-0.0845,-0.0013] | -0.0233 [-0.0652,-0.0045] |

### Panel D — Three-bucket by era (pooled / 2025_lychee / 2026_collector)

| thresh | era | direction | N jumps | same (%) | zero (%) | opposite (%) |
|:-----|:---|:--------|:------|:-------|:-------|:-----------|
| >=3c | pooled | K->PM | 219 | 122 (55.7%) | 38 (17.4%) | 59  (26.9%) |
| >=3c | pooled | PM->K | 237 | 102 (43.0%) | 102 (43.0%) | 33  (13.9%) |
| >=3c | 2025_lychee | K->PM | 183 | 97 (53.0%) | 32 (17.5%) | 54  (29.5%) |
| >=3c | 2025_lychee | PM->K | 197 | 82 (41.6%) | 86 (43.7%) | 29  (14.7%) |
| >=3c | 2026_collector | K->PM | 36 | 25 (69.4%)* | 6 (16.7%) | 5  (13.9%) |
| >=3c | 2026_collector | PM->K | 40 | 20 (50.0%) | 16 (40.0%) | 4  (10.0%) |
| >=5c | pooled | K->PM | 110 | 59 (53.6%) | 20 (18.2%) | 31  (28.2%) |
| >=5c | pooled | PM->K | 81 | 45 (55.6%) | 26 (32.1%) | 10  (12.3%) |
| >=5c | 2025_lychee | K->PM | 100 | 52 (52.0%) | 19 (19.0%) | 29  (29.0%) |
| >=5c | 2025_lychee | PM->K | 64 | 36 (56.2%) | 19 (29.7%) | 9  (14.1%) |
| >=5c | 2026_collector | K->PM | 10 | 7 (70.0%) | 1 (10.0%) | 2  (20.0%) |
| >=5c | 2026_collector | PM->K | 17 | 9 (52.9%) | 7 (41.2%) | 1  (5.9%) |

*2026_collector 69.4% PENDING ROBUSTNESS: fight-clustered bootstrap CI [-0.023, +0.374], p=0.076 — does not survive clustering at N=36 jumps / 91 fights. See qa/phase2_asymmetry_robustness_v2.md. Direction consistent with pooled finding; underpowered due to small N. The pooled 3c result (+12.7pp, p=0.012) survives and is dominated by 2025_lychee era.

**2026 PM venue-coverage caveat:** 2026_collector PM sourced from global Polymarket CLOB only (data-api.polymarket.com); US QCX order flow excluded. See Ex6.

**2026 asymmetry staleness confound:** 2026 PM books are ~3x thinner per fight (median 154 vs 422 trades in 2025). Thin PM books increase the probability that PM prices are stale at the moment of a Kalshi jump, mechanically inflating the K→PM same-direction rate (K moves first simply because PM hasn't traded yet). This staleness confound cannot be ruled out from the current data and is an additional reason to treat the 2026 asymmetry estimate (+19.4pp at 3c) as preliminary. The 2025_lychee result (+11.4pp, p=0.044) is less susceptible: Lychee captures all on-chain CLOB fills, and PM book depth is substantially higher.
