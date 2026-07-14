# Exhibit Manifest
**Generated:** code/exhibit_freeze.py
**Bootstrap:** B=1000, seed=42, two-stage (per-fight stats → resample fight rows)
**Total runtime:** 5.8s

| Exhibit | Files | Source panel | Source QA | Description |
|:--------|:------|:------------|:----------|:------------|
| 1 | ex1_sample.{csv,md} | phase2_full_panel.parquet | — | Sample counts, coverage, gap levels |
| 2 | ex2_ccf.{csv,md} | phase2_full_panel.parquet | qa/phase2_prototype_leadlag.md | CCF k=−6..+6, two strata, Fisher-z |
| 3 | ex3_jump.{csv,md} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md, qa/phase2_asymmetry_robustness.md | Jump anatomy: 3-bucket + persistent/transient |
| 4 | ex4_gap.{csv,md} | phase2_full_panel.parquet | qa/phase2_full_jump_anatomy.md, qa/phase2_jump_inference.md | Gap closure by tier |
| 5 | ex5_ownflow.{csv,md} | — (hardcoded from QA) | qa/phase1_quintile_sort.md, qa/trackB_phase1_holdout_score.md, qa/trackB_confirmatory_score.md | Phase 1 OFI quintile sort summary |

## Key parameters
- pm_flip exclusions: ['20250823_MUDBOR', '20250906_HARFER', '20250906_SAIRUF']
- Jump threshold (Panel A): 3¢
- Jump threshold (Panel B): 5¢
- Persistence: ≥50% of jump survives 60 min (2 bars at 30-min)
- Gap open: 5¢ → close: 2¢
- Tier: main_event = top 10th decile by combined K+PM volume (≥2,429,505)
- 5-min stratum: fights with co-active% ≥ 25% (10 fights)
- 30-min stratum: all 179 fights
