## Exhibit 7 — Asymmetry Robustness
**Source:** `data/clean/phase2_full_panel.parquet`, 30-min co-active bars.
**Bootstrap:** fight-clustered, B=1000, seed=42.
**same-dir diff:** K->PM same-rate minus PM->K same-rate.
**zero-resp diff:** K->PM zero-rate minus PM->K zero-rate.
`*` = 95% CI excludes zero.

### 7A — Full robustness table

| era | thresh | K N | K same% | K zero% | PM N | PM same% | PM zero% | same-dir diff [95% CI] | zero-resp diff [95% CI] | same-dir survives | zero-resp survives |
|:---|:-----|:---|:------|:------|:---|:-------|:-------|:---------------------|:----------------------|:----------------|:-----------------|
| pooled | 3c | 219 | 54.8% | 18.7% | 266 | 39.5% | 47.4% | +15.3pp [+3.4,+26.1]* | -28.6pp [-39.5,-18.3]* | YES * | YES * |
| pooled | 5c | 110 | 53.6% | 19.1% | 79 | 51.9% | 32.9% | +1.7pp [-21.5,+13.7] | -13.8pp [-28.0,+4.2] | no | no |
| 2025_lychee | 3c | 183 | 51.9% | 19.1% | 226 | 37.6% | 48.7% | +14.3pp [+1.8,+26.4]* | -29.5pp [-42.3,-18.3]* | YES * | YES * |
| 2025_lychee | 5c | 100 | 52.0% | 20.0% | 62 | 51.6% | 30.6% | +0.4pp [-24.0,+15.7] | -10.6pp [-26.7,+9.7] | no | no |
| 2026_collector | 3c | 36 | 69.4% | 16.7% | 40 | 50.0% | 40.0% | +19.4pp [-13.9,+34.8] | -23.3pp [-44.5,+0.4] | no | no |
| 2026_collector | 5c | 10 | 70.0% | 10.0% | 17 | 52.9% | 41.2% | +17.1pp [-38.5,+45.2] | -31.2pp [-58.3,-1.6]* | no | YES * |

### 7B — Survivors summary

| era/thresh | same-dir survives? | zero-resp survives? | verdict |
|:---------|:-----------------|:------------------|:------|
| pooled/3c | YES * | YES * | BOTH |
| pooled/5c | no | no | NEITHER |
| 2025_lychee/3c | YES * | YES * | BOTH |
| 2025_lychee/5c | no | no | NEITHER |
| 2026_collector/3c | no | no | NEITHER |
| 2026_collector/5c | no | YES * | ZERO-ONLY |
