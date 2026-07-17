# Exhibit Manifest
**Generated:** code/exhibit_freeze.py
**Bootstrap:** B=1000, seed=42, two-stage (per-fight stats -> resample fight rows); fight-clustered (ex3 contrast, ex7)
**Total runtime:** 33.2s
**Panel:** combined 2025_lychee (N=181) + 2026_collector (N=100) = 281 fights
**2025 era:** Polymarket API replacement (complement-fix, pm_gapfill_crosswalk.py)
**2026 era:** Polymarket API collector (pm_gapfill.py)

| Exhibit | Files | Source panel | Source QA | Description |
|:--------|:------|:------------|:----------|:------------|
| 1 | ex1_sample.{csv,md} | phase2_full_panel.parquet | -- | Sample counts, coverage, gap levels (pooled + per-era) |
| 2 | ex2_ccf.{csv,md} | phase2_full_panel.parquet | qa/phase2_prototype_leadlag.md | CCF k=-6..+6, two strata, Fisher-z (pooled + per-era) |
| 3 | ex3_jump.{csv,md} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md, qa/phase2_asymmetry_robustness.md | Jump anatomy: 3-bucket + persistent/transient + P-T contrast (pooled + per-era) |
| 4 | ex4_gap.{csv,md} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md | Gap closure by tier (pooled + per-era) |
| 5 | ex5_ownflow.{csv,md} | -- (hardcoded from QA) | qa/phase1_quintile_sort.md, qa/trackB_phase1_holdout_score.md, qa/trackB_confirmatory_score.md | Phase 1 OFI quintile sort summary |
| 6 | ex6_pm_depth.{csv,md} | phase2_full_panel.parquet | -- | PM depth per fight by era; fragmentation ratio (frag_ratio=0.8063) |
| 7 | ex7_asymmetry.{csv,md} | phase2_full_panel.parquet | qa/phase2_asymmetry_robustness_v2.md | Asymmetry robustness: same-dir + zero-resp diffs, fight-clustered CI, survivors |

## Key parameters
- pm_flip exclusions: ['20250906_HARFER']
- Jump threshold (Panel A): 3c
- Jump threshold (Panel B): 5c
- Persistence: >=50% of jump survives 60 min (2 bars at 30-min)
- Gap open: 5c -> close: 2c
- Tier: main_event = top 10th decile by combined K+PM volume (>=1,380,890)
- 5-min stratum: fights with co-active% >= 25% (15 fights, pooled)
- 30-min stratum: all 281 fights (pooled); 2025=181, 2026=100
- Fragmentation ratio: 0.8063 (stop-gate [0.4,1.0]: PASS) — see note below
- MCGHOL (20260711_MCGHOL): in panel, 0.9% co-active — see ex6 detail row

---

## Complement-leg correction (2025 PM data)

**Mechanism.** The Polymarket CTF binary-market contract emits two `OrderFilled` events per
trade: one for the taker leg (genuine) and one for the complementary token leg (synthetic
duplicate). The Lychee on-chain archive indexes all CTF ERC-1155 transfers without
distinguishing legs, so every 2025 PM trade appeared twice in the raw interim file
(once as taker, once as complement). This inflated 2025 PM trade counts and volume by
approximately 2.16×, and biased 5-min VWAP prices because the complement leg records the
mirrored price (1 − p) relative to the taker leg.

**Discovery.** The duplication was identified via API cross-check: a sample of 5 markets
pulled from data-api.polymarket.com yielded counts approximately half those in the
Lychee-derived interim. Initial diagnosis pointed to a YES-token filter, but further
investigation (qa/complement_fix_verification.md) showed that complement fills are
symmetric — NO-token trades generate YES-token complement events — making simple
token-membership filtering unreliable. The only clean solution is to re-source 2025 data
directly from the Polymarket data-api, which returns single-leg (taker-perspective) fills.

**Remediation.** Code/pm_gapfill_crosswalk.py pulled all 185/186 crosswalk-matched markets
from the Polymarket data-api (START_TS 2023-01-01, checkpointed). The replacement data was
verified via two-threshold stop-gate: count ratio ∈ [0.98, 1.02] and 5-market VWAP MAD
< 0.01. All 3 in-scope audit markets passed (MADs 0.0008, 0.0067, 0.0005) after correcting
price orientation via asset token ID comparison against the crosswalk NO token.

**Cite trail.** Concern first logged by Tsang & Yang during manuscript review. Formal audit:
qa/burn_filter_audit.md (settlement ops absent, complement duplication confirmed).
Complement-filter attempt and failure: qa/complement_fix_verification.md.
API pull verification (three runs, third PASS): qa/complement_fix_verification.md §3.
Merge and panel rebuild: pm_merge_lychee_replacement.py; phase2_combined_panel_build.py.
Side audit of rebuilt panel: qa/phase2_side_audit.md (0 flags, 204 eligible fights).
Exhibit diff: qa/complement_fix_diff.md.

---

## Era-thinness note (corrected)

The 2025_lychee era label reflects the original Lychee data provenance; the underlying
trade data has been fully replaced by API pulls (pm_gapfill_crosswalk.py). After correction:

- 2025_lychee: median 191 PM trades/fight, median 161 K trades/fight (Kalshi was relatively
  thin during the 2025 window — early-stage market, May–Nov 2025).
- 2026_collector: median 154 PM trades/fight, median 1,652 K trades/fight (Kalshi grew ~10×
  in volume between eras; PM activity is roughly stable per fight).

The pre-correction 2025 era showed ~382 PM trades/fight (median), yielding a spurious
fragmentation ratio of ~0.36× (2026 ÷ 2025). That figure reflected complement duplication,
not genuine PM activity. **The 0.36× fragmentation ratio is retired and must not be cited.**
The corrected ratio is **0.81×** (154 ÷ 191), indicating broadly comparable per-fight PM
depth across both eras. The apparent era asymmetry in the panel is driven by Kalshi volume
growth, not PM attrition.

---

## Single-vintage statement

**All paper numbers in ex1–ex7 are from a single freeze run on 2026-07-17.**
Source script: `code/exhibit_freeze.py`. Bootstrap seed: 42. Panel vintage:
`data/clean/phase2_full_panel.parquet` rebuilt 2026-07-17 from API-sourced interim
(`data/interim/polymarket_ufc_trades.parquet`, complement-fix applied).
No number in any exhibit was computed from a different panel vintage or a partial run.
The deprecated Lychee-contaminated panel is archived at
`data/raw/polymarket_ufc_trades_lychee_deprecated.parquet` for reproducibility of
the contamination analysis in qa/ only; it must not be used for any paper table.
