# Paper Brief — Headline Numbers
**Project:** UFC cross-venue price discovery (Kalshi × Polymarket, Phase 2)
**Exhibit vintage:** 2026-07-17 (single run, code/exhibit_freeze.py, seed=42)
**Panel:** data/clean/phase2_full_panel.parquet — 281 fights, 2025-05-10 to 2026-07-18

All numbers below cite the exhibit freeze; the source exhibit is noted in brackets.

---

## Sample [ex1]

| Metric | Value |
|:-------|------:|
| Fights analyzed | 281 (181 × 2025_lychee + 100 × 2026_collector) |
| Fight cards | 35 |
| Date range | 2025-05-10 — 2026-07-18 |
| Total 5-min bars | 183,924 |
| Co-active bars (both venues traded) | 18,624 (10.1%) |
| Co-active share p10/p50/p90 (per fight) | 2.1% / 5.8% / 19.0% |
| Kalshi trades | 1,222,785 |
| Kalshi volume (contracts) | 160,112,424 |
| PM trades | 85,346 |
| PM notional (USDC) | 24.9M |
| Mean gap K − PM (co-active bars) | +0.0046 (Kalshi priced 0.46pp above PM) |
| Mean \|gap\| (co-active bars) | 0.0120 (1.2¢) |

---

## Cross-venue correlation [ex2]

| Stratum | k=0 rho | 95% CI | Significant? |
|:--------|:-------:|:------:|:------------:|
| 5-min (15 fights, both%≥25%) | +0.103 | [+0.007, +0.227] | YES |
| 30-min (225 fights) | +0.204 | [+0.138, +0.280] | YES |

No systematic lead-lag: non-zero lags carry no consistent signal beyond k=0.

---

## Jump anatomy — asymmetry [ex3, ex7]

**3¢ threshold, 30-min bars, pooled (281 fights):**

| Direction | N | Same-dir |
|:----------|--:|:--------:|
| K→PM | 219 | 54.8% |
| PM→K | 266 | 39.5% |
| Diff (K−PM) | — | **+15.3pp [+3.4, +26.1]** |

Asymmetry survives fight-clustered bootstrap at 3¢; does not survive at 5¢ (diff +1.7pp,
CI includes zero). Asymmetry is a small-jump phenomenon.

**Zero-response diff (3¢, pooled): −28.6pp [−39.5, −18.3].** PM→K zero-response rate is
~29pp higher than K→PM, reflecting Kalshi's cent-grid discretisation (microstructure
artifact, not information asymmetry).

---

## Jump anatomy — propagation [ex3]

**Persistent-minus-Transient contrast, fight-clustered bootstrap CI:**

| Direction | +1h contrast | 95% CI | Significant? |
|:----------|:-----------:|:------:|:------------:|
| K→PM | +0.044 | [+0.006, +0.093] | YES |
| PM→K | +0.034 | [+0.006, +0.070] | YES |

Both directions: persistent price moves propagate ~4¢ to the other venue by +1h; transient
moves show no propagation. Interpretation: information-driven jumps cross venues; noise
does not.

**Level descriptives (not citable standalone — use contrast CI above):**

| Direction | Class | N | same | +1h | +2h |
|:----------|:------|--:|:---:|:---:|:---:|
| K→PM | PERSISTENT | 129 | +0.021 | +0.022 | +0.017 |
| K→PM | TRANSIENT | 59 | +0.012 | −0.029 | −0.010 |
| PM→K | PERSISTENT | 156 | +0.020 | +0.013 | +0.015 |
| PM→K | TRANSIENT | 88 | +0.002 | −0.021 | −0.018 |

---

## Gap closure [ex4]

| Tier | N episodes | Median (min) | 95% CI | <30m | <2h |
|:-----|:----------:|:------------:|:------:|:----:|:---:|
| main_event | 12 | 32 | [10, 80] | 50% | 83% |
| undercard | 144 | 118 | [82, 175] | 25% | 50% |

Gap threshold: open at 5¢, close at 2¢, ACTIVE type only (both venues trading).
Main-event gaps close in ~32 minutes median; undercard in ~2 hours.

---

## Within-venue order flow (Phase 1, Kalshi) [ex5]

Confirmatory result (26 fight cards, Feb–Nov 2025):
Volume-scaled OFI Q5-Q1 lag-1 spread = **−1.13 ct (SE=0.179, t=−6.29, p<0.001)**.
Short-horizon reversal: high OFI in interval t predicts lower price in t+1.
Effect is sub-tick relative to round-trip fee (~3.45 ct at median price P=0.44).

---

## PM depth and fragmentation [ex6]

| Era | N fights | PM trades/fight (med) | K trades/fight (med) | Co-active bars/fight (med) |
|:----|:--------:|:--------------------:|:-------------------:|:-------------------------:|
| 2025_lychee | 181 | 191 | 161 | 30 |
| 2026_collector | 100 | 154 | 1,652 | 50 |

### Fragmentation ratio

The era-to-era ratio of median PM trades per fight — a measure of whether PM liquidity
is stable across eras — is **0.81×** (154 ÷ 191). Both eras are now sourced identically
from the Polymarket data-api; the comparison is valid.

The ratio of 0.81 reflects a modest decline in per-fight PM activity in 2026 relative to
2025, consistent with Polymarket's UFC coverage changing over time. It does not reflect
a collapse in PM liquidity: PM provides 154 trades per fight median in 2026, comparable
to 2025's 191.

The dominant era difference is on the **Kalshi side**: median K trades/fight grew from 161
(2025) to 1,652 (2026), a roughly 10× increase. The apparent thinning of the cross-venue
panel in 2025 is a Kalshi phenomenon, not a PM one.

**Retired figure.** An earlier draft cited a fragmentation ratio of approximately 0.36×.
That figure was computed from complement-contaminated 2025 PM data (Lychee on-chain
archive, double-counting complement fills). It is incorrect and must not be cited.
The corrected ratio is 0.81×, explicitly recorded in paper/exhibits/MANIFEST.md as of
2026-07-17.

---

## Asymmetry robustness survivors [ex7]

| Spec | Same-dir survives? | Zero-resp survives? |
|:-----|:-----------------:|:------------------:|
| pooled / 3¢ | **YES** +15.3pp [+3.4, +26.1] | **YES** −28.6pp [−39.5, −18.3] |
| pooled / 5¢ | no | no |
| 2025_lychee / 3¢ | **YES** +14.3pp [+1.8, +26.4] | **YES** −29.5pp [−42.3, −18.3] |
| 2025_lychee / 5¢ | no | no |
| 2026_collector / 3¢ | no (N=36, underpowered) | no |

---

## Single-vintage guarantee

**Exhibits ex1 through ex7 are produced by one script (`code/exhibit_freeze.py`),
one run, one timestamp (2026-07-17 13:42 UTC), fixed seed=42.**

All 14 output files (7 × {csv, md} plus MANIFEST.md) carry identical modification
timestamps. No number from any exhibit was backfilled, cherry-picked across runs, or
sourced from a different panel vintage. The panel itself was rebuilt once (2026-07-17)
from the complement-corrected interim file; the deprecated Lychee-contaminated file
is archived and sealed.
