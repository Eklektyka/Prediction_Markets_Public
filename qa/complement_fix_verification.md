# Complement-Leg Fix — Verification Report
Date: 2026-07-17

## VERDICT: STOP-GATE FAILED — no files modified

## Filter Attempted (in memory only)
YES-token filter: keep rows where `maker_asset_id == YES_token OR taker_asset_id == YES_token`
(YES_token = crosswalk.clob_token_ids[0] per market). 2025-era rows only.

## In-Memory Row Counts (NOT written to disk)
| Era | Before | After (proposed) | Retained |
|-----|-------:|-----------------:|---------:|
| 2025 | 437,695 | 302,508 | 69.1% |
| 2026+ | 95,514 | 95,514 | 100% |
| Total | 533,209 | 398,022 | 74.6% |

## Stop-Gate Verification Table
| Market | Raw | Filtered | API | Ratio | VWAP MAD | Result |
|--------|----:|---------:|----:|------:|---------:|--------|
| ufc-radtke-vs-frunza-2025-11-01 | 500 | 268 | 230 | 1.1652 | 0.0665 | **FAIL** |
| ufc-wood-vs-delgado-2025-10-25 | 705 | 451 | 323 | 1.3963 | 0.1217 | **FAIL** |
| ufc-fight-night-bleda-vs-horth-358-281 | 930 | 930 | 452 | 2.0575 | 0.0035 | **FAIL** |
| ufc-fight-night-usman-vs-buckley | 1450 | 839 | 637 | 1.3171 | 0.1676 | **FAIL** |
| ufc-man1-bra6-2025-12-13 | 2925 | 2925 | 1402 | 2.0863 | 0.2242 | **FAIL** |

Thresholds: ratio ∈ [0.98, 1.02], VWAP MAD < 0.01

## Failure Analysis

Two independent root causes, both confirmed by deeper diagnostics.

### Root cause 1: Two of five audit markets absent from crosswalk

Markets 550473 (bleda-vs-horth) and 839660 (man1-bra6) are not present in
`ufc_crosswalk.parquet`. Yes-token is unknown → filter applied nothing → ratio 2.06×.

Overall 2025 population: 989 unique markets in the interim file; only 185 are in the
crosswalk (61.2% of rows covered). The YES-token filter is blind to the other 38.8%.

### Root cause 2: Complement fills are SYMMETRIC — YES-only filter is incomplete

The CTF contract emits **two** OrderFilled events per binary trade, symmetrically:

| Trade type | Primary event (genuine) | Complement event (duplicate) |
|---|---|---|
| User buys YES | maker_asset_id=YES, taker_asset_id=USDC | maker_asset_id=USDC, taker_asset_id=NO |
| User buys NO  | maker_asset_id=NO,  taker_asset_id=USDC | **maker_asset_id=YES, taker_asset_id=USDC** |

For NO buys, the complement event is a YES-token row. The YES-only filter retains it
(incorrectly), which is why ratio > 1.0 even after filtering:

| Market | YES rows | Pure-YES (no NO in block) | Complement-YES (from NO trades) | API |
|--------|----------:|--:|--:|--:|
| radtke  (648861) | 268 | 72 | 196 | 230 |
| wood    (639347) | 451 | 181| 270 | 323 |
| buckley (550463) | 839 | 266| 573 | 637 |

### Root cause 3: Block-dedup is unreliable

Polygon block time is ~2 seconds. Independent trades from different users regularly
land in the same block. "YES row and NO-only row share a block_number" does NOT
reliably indicate complement fills — they could be two unrelated trades. The
block-dedup projection (107, 198, 303) is far below API (230, 323, 637), confirming
the approach under-counts by ~50%.

### Conclusion: transaction hashes are required

The only clean deduplication is on `(transaction_hash, YES_token_presence)`:
for each on-chain transaction, keep the row where `taker_asset_id == YES_token`.
Transaction hashes exist in the raw Lychee archive chunks but were dropped by
`pm_trades_append.py` (only reads block_number + amounts). They are NOT
recoverable from the current interim file.

## Remediation Options

**(A) Re-extract 2025 from Lychee archive with tx_hash**: modify pm_trades_append.py
to also read `transaction_hash` from raw chunks; deduplicate per (tx_hash, market_id)
keeping only the YES-token row per transaction. Requires full archive scan for 2025
markets (~same duration as original extraction). Produces ~1 row per trade.
Effort: medium (3–4 hours including validation).

**(B) Replace 2025 Lychee leg with data-api pulls**: extend pm_gapfill.py's `START_TS`
back to 2023-01-01 and re-pull the entire history from `data-api.polymarket.com`.
The data-api is the authoritative single-leg source; no complement fills by design;
already battle-tested in this codebase. Covers ALL markets (not just the 185 in the
crosswalk). Effort: low (1–2 hours of run time; minimal code change).

**(C) Future-only fix (pm_trades_append.py)**: add `transaction_hash` to the column
read list in the archive scan and deduplicate per (tx_hash) keeping YES-token rows.
Fixes new appends only; historical 2025 data remains contaminated.

**Recommendation**: Option B for correctness, speed, and completeness. The gapfill
infrastructure already exists; it only needs a date-range extension. Option A is
preferable if Lychee provenance must be preserved for all eras.

STOPPED. No files modified. Awaiting confirmation.

## Elapsed: 14s

---

## pm_gapfill_crosswalk.py — API Pull Verification (2026-07-17)

### Run summary
- Markets pulled: 185 / 186 crosswalk markets
- Total API rows: 123,896
- Date range: 2025-05-05 -> 2025-11-28
- START_TS: 2023-01-01
- Output staged: C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public\data\interim\pm_api_2025.parquet

### 5-Market Verification Table
| Market | In scope | Staged | Prior API | Ratio | VWAP MAD | Result |
|--------|:--------:|-------:|----------:|------:|---------:|--------|
| ufc-radtke-vs-frunza-2025-11-01 | Y | 230 | 230 | 1.0000 | 0.0665 | **FAIL** |
| ufc-wood-vs-delgado-2025-10-25 | Y | 323 | 323 | 1.0000 | 0.1217 | **FAIL** |
| ufc-fight-night-bleda-vs-horth-358-281 | N (OOS) | 0 | 452 | N/A | N/A | **OOS** |
| ufc-fight-night-usman-vs-buckley | Y | 637 | 637 | 1.0000 | 0.1676 | **FAIL** |
| ufc-man1-bra6-2025-12-13 | N (OOS) | 0 | 1402 | N/A | N/A | **OOS** |

Thresholds: ratio in [0.98, 1.02], VWAP MAD < 0.01.
In-scope markets: 0/3 passed.

### VERDICT: STOP-GATE FAILED
0/3 in-scope audit markets passed. pm_api_2025.parquet
written but NOT merged into interim. Investigate failing markets before proceeding.

Elapsed: 295s

---

## pm_gapfill_crosswalk.py — API Pull Verification (2026-07-17)

### Run summary
- Markets pulled: 185 / 186 crosswalk markets
- Total API rows: 123,896
- Date range: 2025-05-05 -> 2025-11-28
- START_TS: 2023-01-01
- Output staged: C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public\data\interim\pm_api_2025.parquet

### 5-Market Verification Table
| Market | In scope | Staged | Prior API | Ratio | VWAP MAD | Result |
|--------|:--------:|-------:|----------:|------:|---------:|--------|
| ufc-radtke-vs-frunza-2025-11-01 | Y | 230 | 230 | 1.0000 | 0.0665 | **FAIL** |
| ufc-wood-vs-delgado-2025-10-25 | Y | 323 | 323 | 1.0000 | 0.1217 | **FAIL** |
| ufc-fight-night-bleda-vs-horth-358-281 | N (OOS) | 0 | 452 | N/A | N/A | **OOS** |
| ufc-fight-night-usman-vs-buckley | Y | 637 | 637 | 1.0000 | 0.1676 | **FAIL** |
| ufc-man1-bra6-2025-12-13 | N (OOS) | 0 | 1402 | N/A | N/A | **OOS** |

Thresholds: ratio in [0.98, 1.02], VWAP MAD < 0.01.
In-scope markets: 0/3 passed.

### VERDICT: STOP-GATE FAILED
0/3 in-scope audit markets passed. pm_api_2025.parquet
written but NOT merged into interim. Investigate failing markets before proceeding.

Elapsed: 22s

---

## pm_gapfill_crosswalk.py -- API Pull Verification (2026-07-17)

### Run summary
- Markets pulled: 185 / 186 crosswalk markets
- Total API rows: 123,896
- Date range: 2025-05-05 -> 2025-11-28
- START_TS: 2023-01-01
- Checkpointed: yes (data/raw/pm_lychee_repl/)
- Output staged: C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public\data\interim\pm_api_2025.parquet

### 5-Market Verification Table
| Market | In scope | Staged | Prior API | Ratio | VWAP MAD | Result |
|--------|:--------:|-------:|----------:|------:|---------:|--------|
| ufc-radtke-vs-frunza-2025-11-01 | Y | 230 | 230 | 1.0000 | 0.0008 | **PASS** |
| ufc-wood-vs-delgado-2025-10-25 | Y | 323 | 323 | 1.0000 | 0.0067 | **PASS** |
| ufc-fight-night-bleda-vs-horth-358-281 | N (OOS) | 0 | 452 | N/A | N/A | **OOS** |
| ufc-fight-night-usman-vs-buckley | Y | 637 | 637 | 1.0000 | 0.0005 | **PASS** |
| ufc-man1-bra6-2025-12-13 | N (OOS) | 0 | 1402 | N/A | N/A | **OOS** |

Thresholds: ratio in [0.98, 1.02], VWAP MAD < 0.01.
In-scope markets: 3/3 PASS.
Out-of-scope markets (2): not in crosswalk; not pulled; require separate treatment.

### VERDICT: PASS
All 3 in-scope audit markets passed count ratio and VWAP MAD thresholds.
pm_api_2025.parquet is READY TO REPLACE the 2025_lychee rows in the interim file.
Downstream panels NOT rebuilt. Awaiting confirmation to merge.

Elapsed: 11s
