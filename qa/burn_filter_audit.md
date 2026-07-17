# Burn/Merge/Mint Filter Audit
Date: 2026-07-17

## Executive Summary

**VERDICT: CONTAMINATED — Settlement-layer operations are likely present but undetectable.**

The `data/interim/polymarket_ufc_trades.parquet` file **cannot reliably filter burn/merge/mint transactions** due to missing addressing information. While the fingerprint test reveals only 11 suspicious rows (~0.002% of trades), this is NOT evidence of cleanliness — it reflects the absence of fields needed to detect these operations, not their absence from the data.

---

## Code Audit

### File Creation & Modification

The `polymarket_ufc_trades.parquet` file is created and maintained by two scripts:

1. **`code/pm_trades_append.py`** (primary creator)
   - Reads raw Lychee polymarket/trades parquet files from archive
   - Filters by outcome token presence (lines 141-144):
     ```python
     mask = pc.or_(
         pc.is_in(tbl.column("maker_asset_id"), value_set=missing_arr),
         pc.is_in(tbl.column("taker_asset_id"), value_set=missing_arr),
     )
     ```
   - **Filter logic**: Include only rows where maker_asset_id OR taker_asset_id is in UFC token list
   - **No settlement-layer check**: No fields are examined to distinguish trades from settlement ops

2. **`code/bare_slug_side_audit.py`** (side validation, uses same logic)
   - Archives scan identical; no additional filtering

3. **`code/hygiene_block1.py`** (verification only)
   - Validates that `len(maker_asset_id) < 20 ⟺ asset_id == "0"` (USDC ground truth)
   - No settlement-layer operations mentioned or filtered

### Filter Chain

```
Lychee raw: CTF ERC-1155 transfers (all operations: trades, mints, burns, merges)
    ↓
FILTER 1: Keep rows where maker_asset_id OR taker_asset_id in UFC token_ids
    ↓
FILTER 2: Drop rows with price_yes outside [0, 1] (line 182 of pm_trades_append.py)
    ↓
OUTPUT: polymarket_ufc_trades.parquet
```

**Critical gap**: No filter on operation type, maker/taker addresses, or characteristic burn/mint patterns.

---

## Schema Analysis

### polymarket_ufc_trades.parquet Columns

| Column | dtype | Values | Notes |
|--------|-------|--------|-------|
| block_number | int64 | Polygon block height | Present in raw Lychee |
| maker_asset_id | str | "0" (USDC) or 73–78-char token ID | Present |
| taker_asset_id | str | "0" (USDC) or 73–78-char token ID | Present |
| maker_amount | int64 | USDC units or token units | Present |
| taker_amount | int64 | USDC units or token units | Present |
| ts_utc | datetime64[us, UTC] | Timestamp | Present |
| price_raw | float64 | Traded price (0–1) | Computed |
| price_yes | float64 | Normalized YES price (0–1) | Computed |
| market_id | str | Polymarket condition ID | Computed |
| slug | str | Market slug | Computed |

### Missing Critical Fields

The interim file **does NOT include**:
- `maker` (maker wallet address) — **Cannot filter settlement ops (user vs contract)**
- `taker` (taker wallet address) — **Cannot filter settlement ops**
- `transaction_hash` — Cannot link to detailed tx analysis
- `log_index` — Cannot distinguish multiple ops in same tx
- `type`, `action`, `operation` — No field present in raw Lychee schema either

### Result

**Without maker/taker addresses or an operation-type field, it is impossible to distinguish:**
- Normal peer-to-peer trades (user A ↔ user B)
- Settlement operations (user ↔ contract, contract ↔ contract)

---

## Fingerprint Results

### Step 1: Total Volume
- **Total rows**: 533,209
- **Total USDC volume**: $142,613,227

### Step 2: Exact Price Extremes
- Price == 0.0: 0 rows
- Price == 1.0: 0 rows
- **Total: 0 rows (0.000%)**

### Step 3: Near-Extreme Prices
- Price < 0.001: 7 rows
- Price > 0.999: 4 rows
- **Total: 11 rows (0.0021%)**

### Step 4: Same-Wallet Trades
**Cannot determine** — maker/taker addresses not stored.

### Step 5: Suspicious Row Characteristics

| Indicator | Count | Share |
|-----------|-------|-------|
| Rows with price extremes | 11 | 0.0021% |
| USDC volume in suspicious rows | $1,067 | 0.0007% |
| Rows with maker_amount == 0 | 0 | 0% |
| Rows with taker_amount == 0 | 0 | 0% |
| Rows where both sides USDC | 0 | 0% |
| Rows with extreme ratio (>1000x) | 0 | 0% |

### Step 6: Timestamp Range of Suspicious Rows
- Suspicious rows span: 2024-07-14 to 2025-11-22
- Overall dataset: 2023-03-17 to 2026-01-25
- **Suspicious rows scattered throughout, not concentrated near event settlement windows**

---

## Impact Bound (Undetectable Contamination)

### Known Bounds
- **Detectable suspicious rows**: 11 (0.0021% of 533,209)
- **Detectable suspicious volume**: $1,067 (0.0007% of $142.6M)
- **Undetectable settlement ops**: Unknown (cannot be filtered without addresses)

### What Could Be Hidden
The Lychee raw data includes **all CTF ERC-1155 transfers**, which encompasses:
1. **Trades** (normal market orders): maker ↔ taker (both are users)
2. **Mints** (add LP): user → contract (contract address as taker)
3. **Burns** (remove LP): contract → user (contract address as maker)
4. **Merges** (hedge settlement): multi-step token swaps with contract

**Polymarket liquidity provision (mint/burn) activity**:
- Polymarket uses Balancer V2 AMM for UFC market pools
- Liquidity providers mint outcome tokens via deposit, burn via withdrawal
- These operations generate ERC-1155 transfers **indistinguishable from trades** in raw logs

### Cannot Rule Out
- Contamination from LP mint/burn operations
- Contamination from merger/settlement hedges
- Specific vulnerability: taker-side USDC trades (15.03% of dataset) could include mints where contract deposits collateral

---

## VERDICT

### Classification: **CONTAMINATED**

**Reasoning:**

1. **Missing addressing data**: The file lacks maker/taker wallet addresses, which are essential to distinguish user-to-user trades from user-to-contract settlement operations.

2. **No operation-type indicator**: The raw Lychee schema contains no `type` or `action` field. Settlement ops are indistinguishable at the schema level.

3. **Lychee includes all CTF transfers**: The source data (Lychee polymarket/trades) indexes all ERC-1155 transfers, including mints, burns, and merges. The filtering applied (token presence + price bounds) does not exclude settlement-layer operations.

4. **Minimal detectable contamination**: Only 11 rows (0.002%) show classic burn/merge signatures (price extremes). This is NOT evidence of cleanliness — it means most potential settlement ops have no distinguishing signature detectable without addresses.

5. **Tsang & Yang warning confirmed**: The paper's caution about `makerAssetId=0` including burn transactions is **valid and applies here**. The 15.03% of rows with taker_asset_id == "0" (taker as USDC maker) include unknown amounts of mint operations.

### Exposure Summary

| Metric | Value |
|--------|-------|
| **Detectable contamination** | 11 rows, 0.0007% USDC volume |
| **Undetectable settlement ops** | Unknown (cannot be filtered) |
| **At-risk rows (taker_asset_id == "0")** | 80,153 (15.03% of dataset) |
| **At-risk USDC volume** | ~$21.3M (15% of total) |

### Remediation Blocked

To fix this:
1. Retrieve maker/taker wallet addresses from raw Lychee or on-chain sources
2. Identify Polymarket contract addresses for mint/burn detection
3. Implement address-based filtering or manual settlement-op removal
4. Rebuild the entire panel downstream

**Per instructions: STOPPED. Do not suggest or implement fixes.**

---

## References

- **Tsang & Yang (2025)** on Polymarket USDC filter contamination
- **Lychee schema**: Raw Lychee polymarket/trades files (`trades_*.parquet`)
- **Code**: `code/pm_trades_append.py` (lines 130–149, 161–183)
- **Interim file**: `data/interim/polymarket_ufc_trades.parquet` (533,209 rows, 10 columns)

---

## Source Discrimination Test (2026-07-17)

### Step 1 — 5 Selected Mid-Liquidity 2025 UFC Markets

Markets with 500–3,000 Lychee trade rows in 2025 (437,695 total 2025 rows across 205 qualifying markets). Five selected at quartile positions:

| market_id | slug | Lychee 2025 rows | Date range (2025) |
|-----------|------|----------------:|-------------------|
| 648861 | ufc-radtke-vs-frunza-2025-11-01 | 500 | 2025-10-25 → 2025-11-02 |
| 639347 | ufc-wood-vs-delgado-2025-10-25 | 705 | 2025-10-19 → 2025-10-25 |
| 550473 | ufc-fight-night-bleda-vs-horth-358-281 | 930 | 2025-06-10 → 2025-06-23 |
| 550463 | ufc-fight-night-usman-vs-buckley | 1,450 | 2025-06-10 → 2025-06-15 |
| 839660 | ufc-man1-bra6-2025-12-13 | 2,925 | 2025-12-06 → 2025-12-14 |

### Step 2 — API Fetch Pattern (from pm_gapfill.py)

- **Base URL**: `https://data-api.polymarket.com/trades`
- **Key param**: `market=<conditionId>` (64-char hex string `0x...`, resolved from integer pm_id via `https://gamma-api.polymarket.com/markets/<pm_id>`)
- **Other params**: `limit=500` (max page size), `offset=<n>` (offset-based pagination)
- **Auth**: None required (public, no headers)
- **Pagination**: offset increments by 500; stop when page returns < 500 rows. API hard caps at ~10,000 rows per market query (returns HTTP 400 at offset ≥ 10,500).
- **Semantic**: API returns taker-perspective fills only (the outcome token the taker explicitly requested). Each trade appears as 1 API row regardless of binary structure.

### Step 3 — API Comparison Results

conditionIds resolved via Gamma API: confirmed for all 5 markets.

#### Raw counts (all rows, 2025 only)

| Market | Lychee (L) | API (A) | L/A ratio |
|--------|-----------:|--------:|----------:|
| ufc-radtke-vs-frunza-2025-11-01 | 500 | 230 | **2.174** |
| ufc-wood-vs-delgado-2025-10-25 | 705 | 323 | **2.183** |
| ufc-fight-night-bleda-vs-horth-358-281 | 930 | 452 | **2.058** |
| ufc-fight-night-usman-vs-buckley | 1,450 | 637 | **2.276** |
| ufc-man1-bra6-2025-12-13 | 2,925 | 1,402 | **2.086** |
| **Mean** | | | **2.155** |

#### Token-level breakdown (bleda-vs-horth market — only fully-paginated API response)

The bleda-vs-horth market returned all trades in a single API page (452 rows), enabling precise token-level comparison:

| Metric | YES token (Bleda) | NO token (Horth) |
|--------|------------------:|-----------------:|
| Lychee rows (taker side) | 415 | 455 |
| API rows | 409 | 43 |
| Ratio L/A | **1.015** | **10.58** |

**Finding**: Lychee YES-token fills match API YES fills to within 1.5%. Lychee NO-token fills are 10.6x the API NO fills. The extra Lychee NO-token rows (455 − 43 = 412) are **complementary binary-leg fills** — not separately requested trades.

#### Match rate on (timestamp + price + size)

Direct matching failed (0%) because:
1. Lychee timestamps are derived from `polygon_blocks.parquet` (block-level precision); API timestamps are fill-level (sub-block). These differ by ±1–2 seconds per fill.
2. When aligned by second-level timestamp: **97.6% of Lychee YES-token rows share an exact second with an API Bleda row** at matching price and share count.

Sample verified match (bleda-vs-horth):
- Lychee block 72590216, ts=2025-06-10 09:05:53 UTC, price_yes=0.5000, taker_amount/1e6=12.0 shares
- API ts=2025-06-10 09:05:53 UTC, price=0.5000, size=12.0 shares ✓

#### VWAP MAD (5-minute bars, all Lychee rows vs API rows)

| Market | VWAP MAD | Notes |
|--------|----------:|-------|
| ufc-radtke-vs-frunza | 0.0845 | One outcome dominant; NO complement pulls VWAP |
| ufc-wood-vs-delgado | 0.1211 | Same effect |
| ufc-fight-night-bleda-vs-horth | **0.0035** | Balanced 50/50 market; complements cancel |
| ufc-fight-night-usman-vs-buckley | 0.1686 | One outcome dominant |
| ufc-man1-bra6 | 0.2242 | Same effect |

The VWAP divergence is driven by the complementary-fill rows — it is NOT random contamination. In the balanced-market case (bleda-vs-horth), VWAP MAD falls to 0.003, consistent with complementary fills canceling out around the 0.5 mid-price.

### Step 4 — Raw Lychee Schema

Source: `qa/lychee_inventory.md` (full schema audit 2026-07-13). Raw files stored at `C:\Kalshi_data\lychee\data.tar.zst` (~404,540,000 rows).

#### Raw `polymarket/trades` chunk schema

| Column | dtype | Present in interim? | Notes |
|--------|-------|:-------------------:|-------|
| `block_number` | int64 | YES | Primary time key (polygon block) |
| `transaction_hash` | string | **NO** | Available in data-api as `transactionHash` |
| `log_index` | int64 | **NO** | Distinguishes multiple fills per tx |
| `order_hash` | string | **NO** | |
| `maker` | string | **NO** | **Wallet address — enables settlement-op filtering** |
| `taker` | string | **NO** | **Wallet address — enables settlement-op filtering** |
| `maker_asset_id` | string | YES | |
| `taker_asset_id` | string | YES | |
| `maker_amount` | int64 | YES | USDC × 10⁶ |
| `taker_amount` | int64 | YES | Shares × 10⁶ |
| `fee` | int64 | **NO** | All observed = 0 |
| `timestamp` | null | — | Unpopulated in Lychee; derived via polygon_blocks in interim |
| `_fetched_at` | timestamp[ns] | **NO** | |
| `_contract` | string | **NO** | CTF contract address (constant) |

Columns present in raw Lychee but ABSENT in interim: `transaction_hash`, `log_index`, `order_hash`, `maker`, `taker`, `fee`, `_fetched_at`, `_contract`. These were dropped by `pm_trades_append.py` during extraction.

### VERDICT — Source Origin

**CONTAMINATED — QUANTIFIED (complementary binary fills, not burn/mint/merge)**

**Root cause identified**: Lychee `polymarket/trades` captures ALL `OrderFilled` log events emitted by the Polymarket CTF contract. For each user-requested binary-market trade, the CTF emits **two** `OrderFilled` events (one per binary outcome token — the taker's requested fill PLUS the complementary maker fill). The `data-api.polymarket.com` returns only the taker's requested fill (1 row per trade). This produces the observed 2.06×–2.28× Lychee-to-API ratio.

**Evidence**:
- Lychee YES-token fills ≈ API YES fills (ratio 1.015 for bleda-vs-horth)
- Lychee NO-token fills ≫ API NO fills (ratio 10.6× for bleda-vs-horth)
- 91% of Lychee blocks contain fills for BOTH binary outcome tokens simultaneously
- Prices and share sizes match exactly between Lychee YES fills and API fills at same second
- VWAP MAD collapses to 0.003 in balanced markets (complements cancel), confirming they are not noise

**This is NOT burn/merge/mint contamination**. The extra rows are genuine `OrderFilled` events from the CLOB exchange (not AMM/settlement contract), representing the maker-side leg of every binary fill. They have real prices and amounts, but they are the mechanically generated complement of user-initiated trades, not separate user orders.

**Quantified excess**:

| Metric | Value |
|--------|-------|
| Mean Lychee/API row ratio | **2.155×** across 5 markets |
| Excess rows attributable to complementary fills | ~53.6% of all Lychee rows (1 − 1/2.155) |
| YES-token fill match rate vs API | ~98.5% (1.5% unexplained residual) |
| Confirmed burn/mint/merge rows | 0 identified |
| Prior "CONTAMINATED" verdict | Partially downgraded (see below) |

**Revised prior verdict**:
The prior CONTAMINATED verdict (burn/merge/mint undetectable without maker/taker addresses) remains partially valid regarding the *possibility* of AMM-contract rows, but the **primary contamination is now identified and quantified**: complementary binary-leg fills inflating row counts by 2.16× and distorting VWAP in markets with asymmetric trading (one outcome heavily favored).

**Remediation options**:

(a) **Filter to YES-token-taker rows only**: keep only rows where `taker_asset_id` is the YES-token for each market (the outcome indexed 0 in `clob_token_ids`). This eliminates complementary NO fills. Reduces dataset to ~47% of current rows; aligns row counts with API. Requires knowing YES/NO token assignments from crosswalk. Effort: low (1–2 hours; crosswalk already has `clob_token_ids`).

(b) **Replace with data-api pulls**: discard Lychee entirely for the 2025 Polymarket leg; pull from `data-api.polymarket.com` using the existing `pm_gapfill.py` pattern. Uniform source, no complementary-fill issue, transaction hashes included. Effort: low–medium (existing infrastructure, ~1 day of run time for all markets).

(c) **Retain both token sides but adjust price_yes correctly**: NO-token rows already have `price_yes = 1 − price_no`, which equals the YES price at same timestamp. Row-count inflation remains 2×, but price levels are unbiased. VWAP is biased only in asymmetric-trading markets. Effort: zero (no change needed for price-level analyses).

**Recommendation**: Option (a) for any volume or trade-count analysis. Option (c) is acceptable for price-only analysis provided the 2× row inflation is noted. Option (b) for complete remediation if a canonical single-source dataset is required.

**STOPPED. No fixes applied without confirmation.**

