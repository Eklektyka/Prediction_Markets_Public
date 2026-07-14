# Exhibit Manifest
**Panel builder:** code/phase2_combined_panel_build.py → data/clean/phase2_full_panel.parquet
**Exhibit generator:** code/exhibit_freeze.py (Ex1–Ex6 only; Ex7 from QA frozen output)
**Bootstrap:** B=1000, seed=42, two-stage (per-fight stats -> resample fight rows)
**Total runtime:** 16.1s
**Panel:** combined 2025_lychee (N=181) + 2026_collector (N=100) = 281 fights

| Exhibit | Files | Source panel | Source QA | Description |
|:--------|:------|:------------|:----------|:------------|
| 1 | ex1_sample.{csv,md} | phase2_full_panel.parquet | -- | Sample counts, coverage, gap levels (pooled + per-era) |
| 2 | ex2_ccf.{csv,md} | phase2_full_panel.parquet | qa/phase2_prototype_leadlag.md | CCF k=-6..+6, two strata, Fisher-z (pooled + per-era) |
| 3 | ex3_jump.{csv,md} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md, qa/phase2_asymmetry_robustness.md | Jump anatomy: 3-bucket + persistent/transient (pooled + per-era) |
| 4 | ex4_gap.{csv,md} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md | Gap closure by tier (pooled + per-era) |
| 5 | ex5_ownflow.{csv,md} | -- (hardcoded from QA) | qa/phase1_quintile_sort.md, qa/trackB_phase1_holdout_score.md, qa/trackB_confirmatory_score.md | Phase 1 OFI quintile sort summary |
| 6 | ex6_pm_depth.{csv,md} | phase2_full_panel.parquet + pm_gapfill_trades.parquet | qa/phase2_mcghol_diagnosis.md | Supplementary: PM book depth by era (thinness table); venue-coverage caveat |
| 7 | ex7_asymmetry.{csv,md} | phase2_full_panel.parquet | qa/phase2_asymmetry_robustness_v2.md | Supplementary: jump asymmetry robustness — pooled/2025/2026 x 3c/5c, fight-clustered bootstrap CIs |

## Exclusion chain
- Crosswalk: 315 rows total → 186 2025_lychee exact + 113 2026_collector exact = **299 exact-matched UFC fights**
- Panel build: 299 - 17 skipped (zero trades at one/both venues) = **282 fights in panel**
  - 2025 skips (4): GOFSEO, BRAELL, ZIAFER, TAFASL — zero trades both venues
  - 2026 skips (13): CHISTR, TOPGAE + 11 others — zero PM trades (gap-fill has no match)
- Exhibit freeze: 282 - 1 pm_flip excluded = **281 fights analyzed**
  - Excluded: 20250906_HARFER — booking change fight (Fernandes market, 0 co-active bars)
- Additional zero co-active (in panel but contribute nothing to CCF/jump/gap): ALSCAM, NASEST, BUKBEL, HOLSMI

## Data quality note — 2026_collector PM source

The 2026_collector PM leg uses `data-api.polymarket.com/trades?market=<conditionId>` (global
CLOB taker-view). This endpoint **does not include US QCX order flow** (Polymarket's separate
US-licensed order book, launched 2025). US QCX has no public historical API and is therefore
absent from all 2026 PM data. All 2026 per-era columns in Exhibits 1–4 and Ex7 are therefore
based on global-CLOB PM only. This note qualifies every 2026_collector column in Ex1–Ex4 and Ex7.

Magnitude of thinness: 2026 PM median 154 trades/fight vs 2025 Lychee median 422 trades/fight
(0.36x ratio). Bar-level coverage is better preserved (median 91 vs 106 active PM bars/fight,
0.86x). Full era-thinness table in Ex6.

**Implication for findings**: thinness should attenuate PM-side price discovery signals toward
zero, making any 2026 directional consistency with 2025 conservative rather than inflated.
The 2026 asymmetry estimate (+19.4pp at 3c) is directionally consistent but does not survive
fight-clustered bootstrap (p=0.076, N=36 jumps). No 2026-specific claim is made in the paper
without the pooled result also surviving.

**MCGHOL note**: the main win/loss Polymarket market for McGregor vs Holloway (UFC 329,
2026-07-11) had zero pre-fight trading. KO/TKO prop siblings traded actively from 2026-05-19.
Main market opened in-play at 02:05 UTC; t_end=02:45 UTC. 8 PM bars = in-play data only.

## Key parameters
- pm_flip exclusions: ['20250906_HARFER']
- Jump threshold (Panel A): 3c
- Jump threshold (Panel B): 5c
- Persistence: >=50% of jump survives 60 min (2 bars at 30-min)
- Gap open: 5c -> close: 2c
- Tier: main_event = top 10th decile by combined K+PM volume (>=1,380,890)
- 5-min stratum: fights with co-active% >= 25% (15 fights, pooled)
- 30-min stratum: all 281 fights (pooled); 2025=181, 2026=100
- MCGHOL (20260711_MCGHOL): in panel, 840 K_bars, 8 PM_bars, 0.9% co-active
  - PM trades (3,500 total) all concentrated in final 40 min before t_end (in-fight) + post-settlement
  - t_end = 2026-07-12 02:45 UTC; t_start = 2026-07-09 02:45 UTC; no pre-fight PM trading
  - 8 PM bars = in-fight trading only; NOT a timestamp bug
