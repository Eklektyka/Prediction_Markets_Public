## Exhibit 3 — Jump Anatomy (30-min stratum, 281 fights)
**Jump:** |ret| >= threshold on co-active 30-min bars.
**B's response:** B's return on same bar, signed by A's direction.
**Bootstrap:** B=1000, seed=42, two-stage by fight (levels); fight-clustered by fight (contrast).

### Panel A — Three-bucket decomposition (>= 3c jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥3¢) | 219 | 120 (54.8%) | 41 (18.7%) | 58 (26.5%) |
| PM→K (≥3¢) | 266 | 105 (39.5%) | 126 (47.4%) | 35 (13.2%) |
| K→PM same-rate minus PM→K same-rate | — | +15.3pp  95% CI [+3.1, +26.5]pp | — | — |

### Panel B — Three-bucket decomposition (>= 5c jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥5¢) | 110 | 59 (53.6%) | 21 (19.1%) | 30 (27.3%) |
| PM→K (≥5¢) | 79 | 41 (51.9%) | 26 (32.9%) | 12 (15.2%) |
| K→PM same-rate minus PM→K same-rate | — | +1.7pp  95% CI [-21.6, +14.5]pp | — | — |

### Panel C — Persistent vs transient propagation (>= 3c, 30-min bars)
PERSISTENT = A's price still >= 50% of jump after 60 min (2 bars). Values = B's aligned cumulative return. CIs two-stage bootstrap by fight.

| Direction | Class | N | same (mean [95% CI]) | +30m (mean [95% CI]) | +1h (mean [95% CI]) | +2h (mean [95% CI]) |
|:--------|:----|:---|:-------------------|:-------------------|:------------------|:------------------|
| K→PM | PERSISTENT | 129 | +0.0213 [+0.0064,+0.0308] | +0.0140 [+0.0028,+0.0186] | +0.0224 [+0.0064,+0.0283] | +0.0171 [-0.0001,+0.0254] |
| K→PM | TRANSIENT | 59 | +0.0121 [-0.0026,+0.0347] | -0.0226 [-0.1002,-0.0015] | -0.0293 [-0.1031,-0.0042] | -0.0099 [-0.0245,+0.0038] |
| PM→K | PERSISTENT | 156 | +0.0203 [+0.0088,+0.0380] | +0.0072 [-0.0014,+0.0090] | +0.0127 [+0.0012,+0.0144] | +0.0152 [+0.0010,+0.0243] |
| PM→K | TRANSIENT | 88 | +0.0019 [-0.0017,+0.0079] | -0.0167 [-0.0484,+0.0042] | -0.0214 [-0.0611,+0.0004] | -0.0184 [-0.0349,-0.0027] |

### Panel E — Persistent-minus-Transient contrast (fight-clustered bootstrap CI)
**Citable statistic.** Contrast = PERSISTENT mean - TRANSIENT mean per fight, resampled by fight.
`*` = 95% CI excludes zero.

| Direction | Horizon | PERS - TRANS (mean [95% CI]) | CI excludes 0? |
|:--------|:------|:---------------------------|:-------------|
| K→PM | +30m | +0.0238 [-0.0011,+0.0543] | no |
| K→PM | +1h | +0.0439 [+0.0055,+0.0934]* | YES * |
| K→PM | +2h | +0.0268 [-0.0166,+0.0764] | no |
| PM→K | +30m | +0.0156 [-0.0001,+0.0369] | no |
| PM→K | +1h | +0.0340 [+0.0058,+0.0701]* | YES * |
| PM→K | +2h | +0.0423 [+0.0090,+0.0825]* | YES * |

### Panel D — Three-bucket by era (pooled / 2025_lychee / 2026_collector)

| thresh | era | direction | N jumps | same (%) | zero (%) | opposite (%) |
|:-----|:---|:--------|:------|:-------|:-------|:-----------|
| >=3c | pooled | K->PM | 219 | 120 (54.8%) | 41 (18.7%) | 58  (26.5%) |
| >=3c | pooled | PM->K | 266 | 105 (39.5%) | 126 (47.4%) | 35  (13.2%) |
| >=3c | 2025_lychee | K->PM | 183 | 95 (51.9%) | 35 (19.1%) | 53  (29.0%) |
| >=3c | 2025_lychee | PM->K | 226 | 85 (37.6%) | 110 (48.7%) | 31  (13.7%) |
| >=3c | 2026_collector | K->PM | 36 | 25 (69.4%) | 6 (16.7%) | 5  (13.9%) |
| >=3c | 2026_collector | PM->K | 40 | 20 (50.0%) | 16 (40.0%) | 4  (10.0%) |
| >=5c | pooled | K->PM | 110 | 59 (53.6%) | 21 (19.1%) | 30  (27.3%) |
| >=5c | pooled | PM->K | 79 | 41 (51.9%) | 26 (32.9%) | 12  (15.2%) |
| >=5c | 2025_lychee | K->PM | 100 | 52 (52.0%) | 20 (20.0%) | 28  (28.0%) |
| >=5c | 2025_lychee | PM->K | 62 | 32 (51.6%) | 19 (30.6%) | 11  (17.7%) |
| >=5c | 2026_collector | K->PM | 10 | 7 (70.0%) | 1 (10.0%) | 2  (20.0%) |
| >=5c | 2026_collector | PM->K | 17 | 9 (52.9%) | 7 (41.2%) | 1  (5.9%) |
