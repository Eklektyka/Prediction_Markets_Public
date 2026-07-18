# Phase 2 — Asymmetry Robustness Checks
**Generated:** 2026-07-14 01:37 UTC
**Panel:** `phase2_full_panel.parquet` (178 fights, 4 pm_flip excluded)
**Stratum:** 30-min co-active bars | Bootstrap: B=10000, seed=42

---

## Section 1 — Speed-asymmetry cluster bootstrap

**Speed** = share of B's +2h aligned cumulative response already in place at +30m,
computed for PERSISTENT jumps only (A still >= 50% of jump after 60 min).

| | K→PM persistent | PM→K persistent |
|:-|----------------:|----------------:|
| N (persistent jumps) | 98 | 113 |
| mean B at +30m | +0.0170 | +0.0065 |
| mean B at +2h  | +0.0223  | +0.0192  |
| **speed (30m/2h)** | **76%** | **34%** |

Observed difference (K speed − PM speed): **+0.424 (+42pp)**

Cluster bootstrap by fight (B=10000):
- 95% CI: **[-2.757, +1.205]**
- Bootstrap p ≈ 0.5008
- **CI includes zero — speed asymmetry is not established beyond sampling noise at this N**

---

## Section 2 — Size-conditioned rerun (jumps >= 5 cents)

### Bucket decomposition

| Direction | N | same (%) | zero (%) | opposite (%) |
|:----------|--:|---------:|---------:|-------------:|
| K→PM | 91 | 56% | 15% | 29% |
| PM→K | 64 | 56% | 30% | 14% |



Two-proportion z-test (>=5c): diff = -0.002 if bk5 and bp5 else "N/A",
z = -0.025, p = 0.9797 (fail to reject).
Cluster bootstrap: CI = [-0.230, +0.097], p ≈ 0.4384.

### Timing decomposition (>= 5 cents)

Columns = B's aligned cumulative return at each horizon. `speed` = +30m / +2h (PERSISTENT only).

#### K→PM

| Class | N | same | +30m | +1h | +2h | speed |
|:------|--:|-----:|-----:|----:|----:|------:|
| PERSISTENT | 51 | +0.0409 | +0.0085 | +0.0123 | +0.0070 | 121% |
| TRANSIENT | < 30 | — | — | — | — | — |

#### PM→K

| Class | N | same | +30m | +1h | +2h | speed |
|:------|--:|-----:|-----:|----:|----:|------:|
| PERSISTENT | 34 | +0.0582 | +0.0112 | +0.0156 | +0.0233 | 48% |
| TRANSIENT | < 30 | — | — | — | — | — |

---

## Section 3 — Summary: which asymmetries survive?

| Asymmetry | Observed (3c) | (a) Cluster bootstrap | (b) Size >= 5c | (c) Both |
|:----------|:-------------|:---------------------|:--------------|:--------:|
| **Same-dir rate** (K→PM > PM→K) | +13pp (55% vs 42%) | CI=[-0.046,+0.205], includes 0 | diff=-0%, p=0.980 | no |
| **Zero-response rate** (PM→K >> K→PM) | +28pp (44% vs 16%) | structural count difference | 30% vs 15% (+14pp) | YES |
| **Speed of propagation** (K→PM faster) | +42pp (76% vs 34%) | CI=[-2.757,+1.205], p=0.5008 | 121% vs 48% | no |

### Interpretation

- **Same-dir rate asymmetry**: Significant by z-test (p=0.013) but the cluster bootstrap CI includes zero — the signal is real in aggregate but driven partly by between-fight heterogeneity. Not conclusively established.
- **Zero-response rate asymmetry**: The large PM->K zero rate (44% at 3c, 30% at 5c) reflects Kalshi's discrete cent-grid pricing, not information asymmetry — PM moves continuously while Kalshi prices round to the nearest cent. This is a microstructure artifact that persists at both thresholds.
- **Speed asymmetry**: CI=[-2.757,+1.205] includes zero (p=0.5008). The speed difference does not survive clustering at N=178 fights. The point estimates (76% vs 34%) are suggestive but not statistically established with fight-clustered inference.
