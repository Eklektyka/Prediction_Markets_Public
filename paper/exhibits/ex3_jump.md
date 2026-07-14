## Exhibit 3 — Jump Anatomy (30-min stratum, 178 fights)
**Jump:** |ret| ≥ threshold on co-active 30-min bars.
**B's response:** B's return on same bar, signed by A's direction.
**Bootstrap:** B=1000, seed=42, two-stage by fight.

### Panel A — Three-bucket decomposition (≥ 3¢ jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥3¢) | 168 | 93 (55.4%) | 26 (15.5%) | 49 (29.2%) |
| PM→K (≥3¢) | 194 | 82 (42.3%) | 85 (43.8%) | 27 (13.9%) |
| K→PM same-rate minus PM→K same-rate | — | +13.1pp  95% CI [-6.4, +22.3]pp | — | — |

### Panel B — Three-bucket decomposition (≥ 5¢ jumps)

| Direction | N jumps | same (%) | zero (%) | opposite (%) |
|:--------|:------|:-------|:-------|:-----------|
| K→PM (≥5¢) | 91 | 51 (56.0%) | 14 (15.4%) | 26 (28.6%) |
| PM→K (≥5¢) | 64 | 36 (56.2%) | 19 (29.7%) | 9 (14.1%) |
| K→PM same-rate minus PM→K same-rate | — | -0.2pp  95% CI [-25.5, +11.9]pp | — | — |

### Panel C — Persistent vs transient propagation (≥ 3¢, 30-min bars)
PERSISTENT = A's price still ≥ 50% of jump after 60 min (2 bars). Values = B's aligned cumulative return. CIs two-stage bootstrap by fight.

| Direction | Class | N | same (mean [95% CI]) | +30m (mean [95% CI]) | +1h (mean [95% CI]) | +2h (mean [95% CI]) |
|:--------|:----|:---|:-------------------|:-------------------|:------------------|:------------------|
| K→PM | PERSISTENT | 98 | +0.0245 [+0.0062,+0.0391] | +0.0170 [+0.0022,+0.0229] | +0.0259 [+0.0051,+0.0354] | +0.0223 [+0.0019,+0.0351] |
| K→PM | TRANSIENT | 47 | +0.0158 [-0.0022,+0.0409] | -0.0284 [-0.1100,-0.0024] | -0.0379 [-0.1281,-0.0063] | -0.0165 [-0.0334,-0.0009] |
| PM→K | PERSISTENT | 113 | +0.0282 [+0.0130,+0.0657] | +0.0065 [-0.0009,+0.0140] | +0.0143 [+0.0030,+0.0214] | +0.0192 [+0.0012,+0.0318] |
| PM→K | TRANSIENT | 65 | +0.0051 [-0.0015,+0.0125] | -0.0252 [-0.0879,+0.0014] | -0.0245 [-0.0839,+0.0026] | -0.0271 [-0.0742,-0.0067] |
