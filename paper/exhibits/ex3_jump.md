## Exhibit 3 — Jump Anatomy (30-min stratum, 179 fights)
**Jump:** |ret| ≥ threshold on co-active 30-min bars.
**B's response:** B's return on same bar, signed by A's direction.
**Bootstrap:** B=1000, seed=42, two-stage by fight.

### Panel A — Three-bucket decomposition (≥ 3¢ jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥3¢) | 183 | 97 (53.0%) | 32 (17.5%) | 54 (29.5%) |
| PM→K (≥3¢) | 194 | 82 (42.3%) | 85 (43.8%) | 27 (13.9%) |
| K→PM same-rate minus PM→K same-rate | — | +10.7pp  95% CI [-5.7, +21.1]pp | — | — |

### Panel B — Three-bucket decomposition (≥ 5¢ jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥5¢) | 100 | 52 (52.0%) | 19 (19.0%) | 29 (29.0%) |
| PM→K (≥5¢) | 64 | 36 (56.2%) | 19 (29.7%) | 9 (14.1%) |
| K→PM same-rate minus PM→K same-rate | — | -4.2pp  95% CI [-27.5, +12.6]pp | — | — |

### Panel C — Persistent vs transient propagation (≥ 3¢, 30-min bars)
PERSISTENT = A's price still ≥ 50% of jump after 60 min (2 bars). Values = B's aligned cumulative return. CIs two-stage bootstrap by fight.

| Direction | Class | N | same (mean [95% CI]) | +30m (mean [95% CI]) | +1h (mean [95% CI]) | +2h (mean [95% CI]) |
|:--------|:----|:---|:-------------------|:-------------------|:------------------|:------------------|
| K→PM | PERSISTENT | 105 | +0.0230 [+0.0063,+0.0393] | +0.0157 [+0.0020,+0.0223] | +0.0244 [+0.0039,+0.0348] | +0.0209 [+0.0019,+0.0339] |
| K→PM | TRANSIENT | 53 | +0.0142 [-0.0025,+0.0396] | -0.0255 [-0.1285,-0.0019] | -0.0336 [-0.1179,-0.0049] | -0.0147 [-0.0332,-0.0011] |
| PM→K | PERSISTENT | 113 | +0.0282 [+0.0132,+0.0654] | +0.0065 [-0.0007,+0.0142] | +0.0143 [+0.0027,+0.0208] | +0.0192 [+0.0011,+0.0326] |
| PM→K | TRANSIENT | 65 | +0.0051 [-0.0013,+0.0125] | -0.0252 [-0.0877,+0.0015] | -0.0245 [-0.0884,+0.0032] | -0.0271 [-0.0740,-0.0070] |
