# Track B Phase 1 — Sample Verification
**Generated:** 2026-07-13  
**Source data:** `data/raw/live/` (35,432 parquet files, deduped on `trade_id`)  
**Reference:** OSF pre-registration commit 7d61b9c

---

## Structural note — no pre-built bar panel

`data/clean/` exists but is **empty**. There is no persisted bar-level parquet.
The analysis panel is constructed at runtime by `trackB_phase1_orderflow.py` and
`trackB_phase1_diagnostics.py` from the raw trade files. All checks below are run
against the same raw-file pipeline those scripts use.

---

## 1. Series present in raw data

| Series | Trades (deduped) | Expected in Track B |
|--------|-----------------|---------------------|
| KXUFCFIGHT | 4,284,174 | **YES — only series used** |
| KXFED (incl. KXFEDDECISION) | 71,369 | Track A only |
| KXCPIYOY | 28,654 | Track A only |
| KXPAYROLLS | 14,412 | Track A only |
| KXU3 | 7,727 | Track A only |
| KXCPICOREYOY | 5,124 | Track A only |

**No macro contamination in Track B.** The analysis scripts filter to
`ticker.startswith("KXUFCFIGHT")` before any computation. The macro trades above
are present in the raw files (collected by the forward collector) but are never
read by the Track B pipeline.

**Flag — 4,146 "OTHER" raw files** whose filenames do not match any of the 7
tracked series prefixes. These files produce zero rows in the trade DataFrame after
the KXUFCFIGHT filter, so they do not affect the analysis. Origin unknown — likely
other Kalshi series collected incidentally or files with a non-standard naming
convention. Low priority; does not affect any current track.

---

## 2. KXUFCFIGHT sample — full raw (including holdout)

| Metric | Value |
|--------|-------|
| Total deduped trades | 4,284,174 |
| Distinct markets (tickers) | 249 |
| Distinct fight stems | 125 |
| Earliest trade | 2026-05-04 00:17:24 UTC |
| Latest trade | 2026-07-13 13:01:30 UTC |

---

## 3. Holdout integrity

| Check | Result |
|-------|--------|
| `.SEALED` sentinel present in `data/holdout/` | **YES** ✓ |
| Holdout fight stems registered | 20 |
| Holdout fights recoverable from raw data | 20 / 20 |
| Holdout trades present in raw files | 1,304,199 |
| Holdout trades excluded by analysis scripts | **YES** ✓ — scripts drop on `fight` stem before any fitting |

The holdout trades exist in `data/raw/` (raw is append-only by design), but every
analysis script excludes them by matching `fight` stems against
`data/holdout/trackB_phase1_holdout_fights.txt` before the coverage floor or any
regression. The `.SEALED` file has not been deleted; holdout has not been scored.

---

## 4. Training set (holdout excluded, ≥ 100 trades per market)

| Metric | Value |
|--------|-------|
| Trades | 2,979,679 |
| Markets (tickers) | 204 |
| Fights | 102 |

Matches the numbers reported in `qa/trackB_phase1_results.txt` (`G=102`) and
`qa/trackB_phase1_diagnostics.txt` (`204 markets, 102 fights`). ✓

---

## 5. Bar panel (5-min buckets, training set)

| Metric | Value |
|--------|-------|
| Total bars | 120,855 |
| Bars with lag-1 dprice (used in regression) | 120,651 |

**Bars per market distribution:**

| min | p25 | median | p75 | max |
|-----|-----|--------|-----|-----|
| 57 | 260 | 359 | 604 | 5,569 |

**Flag — max of 5,569 bars in one market.** The median is 359 bars ≈ 30 hours of
active trading. The maximum of 5,569 bars ≈ 463 hours implies one market traded
across nearly 20 days. This is plausible for a high-profile fight announced weeks
in advance, but is worth a spot-check to confirm it is not a data artefact (e.g.,
a market that never closed and accumulated bars over the full collection window).
Does not affect the aggregate results given the fixed-effects demeaning.

---

## 6. OFI columns

| Column / variant | Present? | Source |
|-----------------|----------|--------|
| Raw signed volume (OFI = yes_count − no_count) | **Constructable** | `taker_side` + `count_fp` in every raw file |
| Within-market z-scored OFI | **NO** | Not pre-computed; not in raw files |
| Large-trade-only OFI | **NO** | Not pre-computed; not in raw files |

**Available building blocks for future OFI variants:**

- `is_block_trade` (bool) — present in every raw file. Can be used directly to
  construct a large-trade-only OFI by filtering to `is_block_trade == True` before
  summing signed counts.
- `taker_book_side` and `taker_outcome_side` — additional taker direction fields
  alongside `taker_side`. Semantics not yet documented; may allow finer-grained
  flow decomposition.

Full raw column list:  
`count`, `count_fp`, `created_time`, `is_block_trade`, `no_price_dollars`,
`series`, `taker_book_side`, `taker_outcome_side`, `taker_side`, `ticker`,
`trade_id`, `yes_price`, `yes_price_dollars`

---

## Summary

| Check | Status |
|-------|--------|
| KXUFCFIGHT only in Track B analysis | PASS |
| Macro series not mixed in | PASS |
| Row / market / fight counts match prior results | PASS |
| Holdout .SEALED sentinel present | PASS |
| Holdout excluded from training set | PASS |
| Raw OFI constructable from taker_side + count_fp | PASS |
| Pre-built z-scored OFI | NOT PRESENT — to build if needed |
| Pre-built large-trade OFI | NOT PRESENT — `is_block_trade` flag available |
| data/clean/ bar panel persisted | NOT PRESENT — constructed at runtime |
| Max bars outlier (5,569) | FLAG — spot-check recommended, low priority |
| 4,146 unrecognised raw files | FLAG — does not affect analysis |
