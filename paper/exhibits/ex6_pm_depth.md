## Exhibit 6 — PM Book Depth by Era (Supplementary)
**Source:** `data/clean/phase2_full_panel.parquet` + `data/interim/pm_gapfill_trades.parquet`
**Purpose:** Quantify whether 2026_collector PM legs are systematically thinner than 2025_lychee.

### PM data source differences

| Property | 2025_lychee | 2026_collector |
|:---------|:-----------|:--------------|
| Raw source | `polymarket_ufc_trades.parquet` (Lychee on-chain dump) | `pm_gapfill_trades.parquet` (Task Scheduler gap-fill) |
| API / origin | CTF ERC-1155 transfers on Polygon mainnet (all CLOB counterparties) | data-api.polymarket.com/trades (taker-view only) |
| US QCX flow included? | Yes (on-chain; QCX routes settle on Polygon) | **No** (data-api returns global CLOB; QCX is a separate book) |
| Timestamp units | Unix ms → converted to ns | Unix s → converted to ns |
| Outcome filtering | One-sided (polymarket_ufc_trades pre-filtered to YES side) | Filter by `outcome == fighters_pm[side_idx]` |

### Panel A — PM trades per fight

| Metric | 2025_lychee (N=182 fights) | 2026_collector (N=100 fights) | Ratio (2026/2025) |
|:-------|:--------------------------|:-----------------------------|:-----------------|
| Fights with any PM trades | 182 (100%) | 100 (100%) | — |
| Median trades/fight | 422 | 154 | **0.36x** |
| p90 trades/fight | 1,520 | 561 | 0.37x |
| Mean trades/fight | 726 | 240 | 0.33x |
| Max trades/fight | 11,639 | 1,183 | — |

### Panel B — PM active bars per fight (5-min bars where pm_n > 0)

| Metric | 2025_lychee | 2026_collector | Ratio |
|:-------|:-----------|:--------------|:------|
| Median active PM bars/fight | 106 | 91 | **0.86x** |
| p90 active PM bars/fight | 277 | 222 | 0.80x |
| Mean active PM bars/fight | 138 | 109 | 0.79x |

### Panel C — Distribution of fights by PM trade count

| PM trades | 2025_lychee | 2026_collector |
|:----------|:-----------|:--------------|
| [1, 10) | 1 | 3 |
| [10, 100) | 5 | 24 |
| [100, 500) | 102 | 62 |
| [500, 1000) | 43 | 10 |
| [1000, 5000) | 29 | 1 |
| [5000+) | 2 | 0 |

### Panel D — MCGHOL (20260711_MCGHOL) detail

| Property | Value |
|:---------|:------|
| condition_id | 0xc851fc5ae688d3d67bccb7c8f0ca475f61ebda796cfcddca7230042de6b48cfd |
| Question | UFC 329: Max Holloway vs. Conor McGregor (Welterweight, Main Card) |
| t_start | 2026-07-09 02:45 UTC |
| t_end | 2026-07-12 02:45 UTC |
| Pre-fight PM trades (t < 2026-07-12) | **0** |
| In-fight PM trades (02:05–02:45 UTC Jul 12) | 517 |
| Post-settlement PM trades (after 02:45 UTC) | 2,983 |
| Total gap-fill trades | 3,500 |
| PM bars in panel (5-min) | 8 (in-fight only) |
| KO/TKO prop siblings | 2 markets; active pre-fight from 2026-05-19 |
| Verdict | Main win/loss market was in-play only; NOT a timestamp bug |

### Interpretation

Bar-level coverage (active bars ratio 0.86x) is much closer to parity than trade-count ratio (0.36x),
meaning 2026 PM prices update at similar frequency but with fewer fills per bar — consistent with
thinner books and wider bid-ask spreads rather than systematic sampling gaps.

The 3x trade-count thinness has two distinct implications:

1. **Gap closure (Ex4):** Thinner 2026 PM liquidity mechanically slows convergence. The 2026
   undercard median closure time (375 min) vs 2025 (115 min) is at least partially attributable
   to PM book depth, not necessarily differences in information linkage.

2. **Jump asymmetry (Ex3):** Thin PM books increase PM price staleness at the moment of a Kalshi
   jump. If PM simply hasn't traded in the bar when Kalshi jumps, that bar is classified as K→PM
   "same-direction" only if PM subsequently moves in the same bar. The staleness confound runs
   in the direction of inflating the K→PM same-direction rate. The 2025_lychee result is less
   susceptible (richer PM data, on-chain source).

**Venue-coverage note:** The missing US QCX flow makes the magnitude of 2026 thinness a lower
bound. If QCX accounts for a meaningful share of UFC betting volume among US-licensed users, the
true 2026 PM book is deeper than what the data-api captures.
