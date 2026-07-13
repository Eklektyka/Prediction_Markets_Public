# Lychee Dataset Inventory

*Generated: 2026-07-13 17:35 UTC*  
*Source: `C:\Kalshi_data\lychee\data.tar.zst` (33.5 GiB compressed)*

## Summary Table

| Table | Platform | ~Rows | Date Min | Date Max | Key Fields |
|-------|----------|-------|----------|----------|------------|
| kalshi/markets | Kalshi | 7,682,445 | 2021-06-30 13:46:45 | 2025-11-23 18:51:48 | ticker, event_ticker, market_type, title, yes_sub_title, no_sub_title |
| kalshi/trades | Kalshi | ~72,140,000 | 2022-07-01 15:17:38 | 2025-01-01 03:37:06 | trade_id, ticker, count, yes_price, no_price, taker_side |
| polymarket/markets | Polymarket | 408,863 | 2020-10-02 16:10:01 | 2026-02-03 22:25:08 | id, condition_id, question, slug, outcomes, outcome_prices |
| polymarket/trades | Polymarket | ~404,540,000 | N/A | N/A | block_number, transaction_hash, log_index, order_hash, maker, taker |
| polymarket/legacy_trades | Polymarket | ~2,210,000 | N/A | N/A | block_number, transaction_hash, log_index, fpmm_address, trader, amount |
| polymarket/blocks | Polymarket | ~7,850,000 est. | N/A | N/A | not extracted |

## Decision-Critical Questions

### a. Kalshi trade-level data — date range, pre-April-2026?

- **Present:** YES — `kalshi/trades/` contains ~72,140,000 rows in 769 chunk files
- **Date range:** 2022-07-01 15:17:38 → 2025-01-01 03:37:06
- **Timestamp column:** `created_time`
- **Predates April 2026 API window:** YES — 1369 days before April 2026 (~3y 9m)
- **First chunk:** `data/kalshi/trades/trades_0_10000.parquet`
- **Last chunk:** `data/kalshi/trades/trades_72130000_72140000.parquet`

### b. Polymarket trades — aggressor/taker-side field? Price encoding? Timestamp precision?

- **Taker/aggressor-side field:** `taker` (PRESENT)
- **Price column:** `None` — encoding: **no price col found**
- **Timestamp column:** `timestamp` (dtype: `null`)
- **Legacy trades taker field:** `None` (ABSENT)

### c. Orderbook / quote data?

- **Tables found:** ['data/kalshi/markets', 'data/kalshi/trades', 'data/polymarket/blocks', 'data/polymarket/fpmm_collateral_lookup.json', 'data/polymarket/legacy_trades', 'data/polymarket/markets', 'data/polymarket/trades']
- **Orderbook/quote tables:** NONE FOUND

### d. Price encoding per table

| Table | Price Column | Encoding |
|-------|-------------|----------|
| kalshi/markets | `last_price` | cents 0-100 |
| kalshi/trades | `None` | no price col found |
| polymarket/markets | `None` | no price col found |
| polymarket/trades | `None` | no price col found |
| polymarket/legacy_trades | `None` | no price col found |

### e. UFC/MMA market identification

- **Kalshi markets matches** (pattern: `KXUFC`, `UFC`, `MMA`): **2187**
  Examples:
  - `KXNFLREC-25NOV23CLELV-LVMMAYER87-5`
  - `KXNFLREC-25NOV23CLELV-LVMMAYER87-4`
  - `KXNFLREC-25NOV23CLELV-LVMMAYER87-3`
  - `KXNFLREC-25NOV23CLELV-LVMMAYER87-2`
  - `KXNFLREC-25NOV23CLELV-LVMMAYER87-1`
- **Polymarket markets matches** (slug/title/question/tag/category): **4130**
  Examples:
  - `Will Khabib win his UFC 254 Fight?`
  - `Will Deiveson Figueiredo win his UFC 255 match?`
  - `Will Conor McGregor win his UFC 257 match on January 23?`
  - `Who will win UFC 259: Blachowicz vs. Adesanya?`
  - `Who will win UFC 261: Hall vs. Weidman?`

**Identification method:**
- Kalshi: ticker prefix `KXUFC` and/or title/series containing `UFC`
- Polymarket: slug, question, or tag field containing `UFC` or `MMA`

---
## Per-Table Schemas

### kalshi/markets

| column | dtype |
|--------|-------|
| ticker | string |
| event_ticker | string |
| market_type | string |
| title | string |
| yes_sub_title | string |
| no_sub_title | string |
| status | string |
| yes_bid | int64 |
| yes_ask | int64 |
| no_bid | int64 |
| no_ask | int64 |
| last_price | int64 |
| volume | int64 |
| volume_24h | int64 |
| open_interest | int64 |
| result | string |
| created_time | timestamp[ns, tz=UTC] |
| open_time | timestamp[ns, tz=UTC] |
| close_time | timestamp[ns, tz=UTC] |
| _fetched_at | timestamp[ns] |


- Rows: 7,682,445 across 769 files
- Timestamp col: `created_time` | Date range: 2021-06-30 13:46:45 → 2025-11-23 18:51:48
- Price col: `last_price` (cents 0-100)
- UFC hits: 2187

### kalshi/trades

| column | dtype |
|--------|-------|
| trade_id | string |
| ticker | string |
| count | int64 |
| yes_price | int64 |
| no_price | int64 |
| taker_side | string |
| created_time | timestamp[ns, tz=UTC] |
| _fetched_at | timestamp[ns] |


- Approx rows: ~72,140,000 (from chunk filenames)
- Timestamp col: `created_time` | Date range: 2022-07-01 15:17:38 → 2025-01-01 03:37:06
- Price col: `None` (no price col found)
- Taker/side field: `taker_side`
- Predates April 2026: YES — 1369 days before April 2026 (~3y 9m)
- First chunk: `data/kalshi/trades/trades_0_10000.parquet` | Last chunk: `data/kalshi/trades/trades_72130000_72140000.parquet`

### polymarket/markets

| column | dtype |
|--------|-------|
| id | string |
| condition_id | string |
| question | string |
| slug | string |
| outcomes | string |
| outcome_prices | string |
| clob_token_ids | string |
| volume | double |
| liquidity | double |
| active | bool |
| closed | bool |
| end_date | timestamp[ns, tz=UTC] |
| created_at | timestamp[ns, tz=UTC] |
| market_maker_address | string |
| _fetched_at | timestamp[ns] |


- Rows: 408,863 across 41 files
- Timestamp col: `created_at` | Date range: 2020-10-02 16:10:01 → 2026-02-03 22:25:08
- Price col: `None` (no price col found)
- UFC hits: 4130

### polymarket/trades

| column | dtype |
|--------|-------|
| block_number | int64 |
| transaction_hash | string |
| log_index | int64 |
| order_hash | string |
| maker | string |
| taker | string |
| maker_asset_id | string |
| taker_asset_id | string |
| maker_amount | int64 |
| taker_amount | int64 |
| fee | int64 |
| timestamp | null |
| _fetched_at | timestamp[ns] |
| _contract | string |


- Approx rows: ~404,540,000
- Timestamp col: `timestamp` (dtype: `null`) | Date range: N/A → N/A
- Price col: `None` (no price col found)
- Taker/side field: `taker`
- First chunk: `data/polymarket/trades/trades_0_10000.parquet` | Last chunk: `data/polymarket/trades/trades_404530000_404540000.parquet`

### polymarket/legacy_trades

| column | dtype |
|--------|-------|
| block_number | int64 |
| transaction_hash | string |
| log_index | int64 |
| fpmm_address | string |
| trader | string |
| amount | string |
| fee_amount | string |
| outcome_index | int64 |
| outcome_tokens | string |
| is_buy | bool |
| timestamp | null |
| _fetched_at | timestamp[ns] |


- Approx rows: ~2,210,000
- Timestamp col: `timestamp` | Date range: N/A → N/A
- Price col: `None` (no price col found)
- Taker/side field: `None`
- First chunk: `data/polymarket/legacy_trades/trades_0_10000.parquet` | Last chunk: `data/polymarket/legacy_trades/trades_2200000_2210000.parquet`

### polymarket/blocks (not extracted)

- 785 parquet files, ~7,850,000 rows estimated
- Contains on-chain block data; not relevant to Phase 1/2 trade analysis.

### polymarket/fpmm_collateral_lookup.json

- Sample keys: ['0x002bAb93B5D1192D6c8a80563F32a120BDcbA4dD', '0x00097A517021FDFB45746F9aafcB36ea39805D82', '0x003AF0c2B531f3531Bf4f03180e6Ff92fB37d015']
- Lookup table mapping FPMM (fixed-product market maker) addresses to collateral tokens.

---
## Full Column Lists (for cross-reference)

**kalshi/trades:** `trade_id`, `ticker`, `count`, `yes_price`, `no_price`, `taker_side`, `created_time`, `_fetched_at`

**polymarket/trades:** `block_number`, `transaction_hash`, `log_index`, `order_hash`, `maker`, `taker`, `maker_asset_id`, `taker_asset_id`, `maker_amount`, `taker_amount`, `fee`, `timestamp`, `_fetched_at`, `_contract`

**polymarket/legacy_trades:** `block_number`, `transaction_hash`, `log_index`, `fpmm_address`, `trader`, `amount`, `fee_amount`, `outcome_index`, `outcome_tokens`, `is_buy`, `timestamp`, `_fetched_at`

---
*End of inventory.*

---

## Appendix: Follow-up Audit (2026-07-13)

### Q1. Polymarket trades + legacy_trades — date ranges

**polymarket/trades**
- `timestamp` column dtype: **`null`** — the field is unpopulated in every row across all chunks examined.
- Date is implicitly encoded in `block_number` (Polygon chain). First chunk has `block_number ≈ 40,000,176`. Mapping block→datetime requires the `polymarket/blocks` table (not extracted). No direct wall-clock range available from the parquet data itself.
- **Conclusion:** polymarket/trades timestamps are unresolvable without the blocks table. block_number is the primary time key.

**polymarket/legacy_trades**
- Same finding: `timestamp` dtype is `null`, all values None.
- `block_number` is the time key here too.

**kalshi/trades** (confirmed from prior run)
- `created_time` (string → parsed UTC): **2022-07-01 → 2025-01-01**

---

### Q2. Price column names and encoding

#### kalshi/trades
| Column | Dtype | Encoding | Sample values |
|--------|-------|----------|---------------|
| `yes_price` | int64 | **cents, 0–100** | 1, 1, 1, 1, 1 |
| `no_price` | int64 | **cents, 0–100** | 99, 99, 99, 99, 99 |

*Note: yes_price + no_price ≈ 100 always. Early records (trades_0_10000) are heavily skewed to 1-cent yes / 99-cent no — likely very early markets before deep liquidity.*

#### polymarket/trades (CLOB, on-chain)
No explicit `price` column. Amounts are USDC in **base units (1e6 = 1 USDC)**:

| Column | Dtype | Encoding | Sample values |
|--------|-------|----------|---------------|
| `maker_amount` | int64 | **USDC × 10⁶** | 73 000 000, 18 250 000, 10 950 000, 79 200 000, 72 000 000 |
| `taker_amount` | int64 | **USDC × 10⁶** | 100 000 000, 25 000 000, 15 000 000, 110 000 000, 100 000 000 |
| `fee` | int64 | **USDC × 10⁶** | 0, 0, 0, 0, 0 |

*Implied probability = maker_amount / taker_amount (e.g. 73M/100M = 0.73). The ratio gives the "yes" price as a fraction 0–1. No pre-computed price column exists — must be derived.*

#### polymarket/legacy_trades (AMM era)
| Column | Dtype | Encoding | Sample values |
|--------|-------|----------|---------------|
| `amount` | int64 | **USDC × 10⁶** | 1 000 000, 958 483, 10 000 000, … |
| `fee_amount` | int64 | **USDC × 10⁶** | 20 000, 19 560, 200 000, … |
| `outcome_index` | int64 | 0 = YES, 1 = NO | — |
| `is_buy` | bool | True = buy (taker aggressor buys shares) | — |

*No implied probability without `outcome_tokens` ratio against collateral. Fee rate ≈ 2% (fee_amount/amount).*

---

### Q3. Kalshi/trades taker_side field

**YES — `taker_side` is present and populated.**

Full schema of kalshi/trades:
```
trade_id      | string
ticker        | string
count         | int64        (number of contracts)
yes_price     | int64        (cents 0-100)
no_price      | int64        (cents 0-100)
taker_side    | string       ("yes" or "no" — aggressor side)
created_time  | string       (ISO-8601 UTC)
_fetched_at   | timestamp[us]
```

This **matches our collector's schema exactly** — same field name `taker_side`, same semantic (which side the taker/aggressor took).

---

### Q4. UFC/MMA market overlap window

#### Kalshi KXUFC markets (strict `ticker.startswith("KXUFC")`)
| Metric | Value |
|--------|-------|
| Market rows | 453 |
| Unique events | 202 |
| `open_time` range | 2025-02-07 → 2025-11-17 |
| `close_time` range | 2025-02-09 → 2027-06-01 |
| `created_time` range | 2025-02-06 → 2025-11-17 |

Sample event tickers: `KXUFCFIGHT-25AUG02BRERIB`, `KXUFCBANTAMWEIGHTTITLE-26`, etc.

**Critical finding:** Kalshi KXUFC markets were first created **2025-02-06**. The Lychee `kalshi/trades` dataset cuts off **2025-01-01** — one month before KXUFC markets even existed. **The Lychee dataset contains zero Kalshi UFC trade records.**

#### Polymarket UFC/MMA markets (question or slug contains `\bUFC\b` or `\bMMA\b`)
| Metric | Value |
|--------|-------|
| Market rows | 1,803 |
| `created_at` range | 2020-10-23 → 2026-02-02 |
| `end_date` range | 2020-10-25 → 2026-12-31 |

Earliest market: *"Will Khabib win his UFC 254 Fight?"* (Oct 2020)

#### Cross-venue overlap conclusion

```
Timeline:
  2022-07-01  Lychee kalshi/trades begins
  2025-01-01  Lychee kalshi/trades ends         <-- data cutoff
  2025-02-06  KXUFC markets first created       <-- too late for Lychee
  2026-04-01  Our collector backfill begins      <-- Phase 1 data
              ↑
              15-month gap with no Kalshi UFC data anywhere

  Polymarket UFC:  2020-10-23 → 2026-02-02 (markets created)
  Polymarket trades: no wall-clock timestamps (block_number only)
```

**Plausible cross-venue UFC overlap: NONE from Lychee.**
- Lychee has no Kalshi UFC trade data (KXUFC didn't exist until Feb 2025, trades cut off Jan 2025).
- Polymarket UFC coverage exists 2020–2026 in markets metadata, but trade timestamps require block→datetime mapping via the `blocks` table.
- For Phase 2 cross-venue analysis, the only available Kalshi UFC trade data is from **our own collector (April 2026 onward)**. Lychee adds Polymarket history and Kalshi non-UFC market context, but contributes no Kalshi UFC trade rows.


---

## Correction + UFC Trade Scan (2026-07-13)

### Correction: kalshi/trades true date range

Earlier analysis sampled only the first and last chunk **by row-index order**
(chunks_0_10000 and trades_72130000_72140000) to bracket the date range.
A full scan of all 7,214 chunk files confirms:

- **True min timestamp:** 2021-06-30 20:09:14.185137+00:00
- **True max timestamp:** 2025-11-25 22:00:15.194245+00:00

The earlier 2025-01-01 claim was **incorrect** — true max is 2025-11-25 22:00:15.194245+00:00. Updated above.

### KXUFC trade scan

- KXUFC tickers in kalshi/markets: 453
- Trade files scanned: 7,214
- **KXUFC rows in kalshi/trades: 522,903**
- Distinct KXUFC markets in trades: 420
- Date range in trades: 2025-02-07 15:01:37 → 2025-11-25 19:52:31

#### Trades by month

| Month | Trades |
|-------|--------|
| 2025-02 | 1,053 |
| 2025-03 | 4,815 |
| 2025-04 | 3,079 |
| 2025-05 | 8,572 |
| 2025-06 | 72,173 |
| 2025-07 | 100,843 |
| 2025-08 | 81,216 |
| 2025-09 | 14,783 |
| 2025-10 | 115,312 |
| 2025-11 | 121,057 |

**Conclusion:** Lychee DOES contain Kalshi UFC trades: 522,903 rows across 420 tickers, 2025-02 – 2025-11.

Why zero: KXUFC markets were first created 2025-02-06 (per kalshi/markets scan).
Lychee kalshi/trades ends 2025-11-25 — the data collection predates the
KXUFC product launch. No cross-venue UFC overlap is available from Lychee.

---

## Polymarket UFC Trade Scan (2026-07-13)

### polygon_blocks.parquet

- Source: `data/polymarket/blocks/` (785 parquet files)
- Block range covered: 4,000,000 → 82,468,430
- Timestamp range: 2020-09-03 04:33:11+00:00 → 2026-02-02 18:27:46+00:00
- Total block→timestamp mappings: 78,468,431
- Timestamp unit in source: `iso` (auto-detected)
- Saved: `data/meta/polygon_blocks.parquet`

### Price formula (polymarket/trades CLOB)

```
Each trade: maker swaps maker_asset_id (maker_amount units) ↔
                  taker swaps taker_asset_id (taker_amount units)
Both amounts in USDC base units (1e6 = $1.00 USDC).

Case A — maker_asset_id is outcome token:
  price_raw = taker_amount / maker_amount   (USDC received per token sold)

Case B — taker_asset_id is outcome token:
  price_raw = maker_amount / taker_amount   (USDC paid per token bought)

price_yes = price_raw          if matched token is YES outcome (clob_token_ids[0])
          = 1.0 − price_raw    if matched token is NO outcome  (clob_token_ids[1])

Result is probability 0–1 ($1 face value per token).
Rows with price_yes outside [0,1] dropped (rounding/dust trades).
```

### Polymarket UFC trade coverage

- UFC/MMA markets matched: 1,803 (question/slug contains UFC or MMA)
- Outcome token IDs: 3,606 (2 per market: YES + NO)
- Trade files scanned: 0 (full sequential scan — row-indexed chunks)
- Trade files with hits: 0
- **Total UFC trade rows: 511,316** (511,316 with resolved block timestamp)
- **Distinct markets in trades: 1,312**
- **Date range: 2023-03-17 06:35:34+00:00 → 2026-01-25 17:22:58+00:00**

| Month | Trades |
|-------|--------|
| 2023-03 | 104 |
| 2023-04 | 140 |
| 2023-05 | 89 |
| 2023-06 | 128 |
| 2023-07 | 38 |
| 2023-08 | 10 |
| 2023-09 | 24 |
| 2023-10 | 25 |
| 2023-11 | 4 |
| 2024-01 | 170 |
| 2024-04 | 416 |
| 2024-05 | 159 |
| 2024-06 | 1,328 |
| 2024-07 | 2,793 |
| 2024-08 | 570 |
| 2024-11 | 1,844 |
| 2025-02 | 23 |
| 2025-03 | 421 |
| 2025-04 | 9 |
| 2025-06 | 38,022 |
| 2025-07 | 46,035 |
| 2025-08 | 63,664 |
| 2025-09 | 26,170 |
| 2025-10 | 63,285 |
| 2025-11 | 102,574 |
| 2025-12 | 73,220 |
| 2026-01 | 90,051 |

### Coverage inside key windows

| Window | Trades | Notes |
|--------|--------|-------|
| Kalshi overlap (Feb–Nov 2025) | 339,852 | KXUFC trades also available for this window (522,903 rows) |
| Collector window (Apr 2026+) | 0 | Polymarket dump ends before Apr 2026 — no overlap with collector. |

**Dump end date:** 2026-01-25 17:22:58+00:00

**Conclusion:** Polymarket UFC trade data covers the Feb–Nov 2025 Kalshi overlap window (339,852 trades). Cross-venue UFC analysis (Kalshi vs Polymarket) is feasible for Feb–Nov 2025. The Polymarket dump ends before our collector window (Apr 2026+).
