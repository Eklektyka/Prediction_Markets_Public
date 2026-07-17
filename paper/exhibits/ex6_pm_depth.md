## Exhibit 6 — PM Depth per Fight
**Source:** `data/clean/phase2_full_panel.parquet`
**Note:** Both eras sourced from Polymarket data-api (2025: pm_gapfill_crosswalk.py; 2026: pm_collector). Volume comparison is valid.
**Fragmentation ratio:** median PM trades/fight(2026) ÷ median PM trades/fight(2025).

### 6A — Depth by era

| Era | N fights | PM trades/fight (med) | PM trades/fight (p90) | K trades/fight (med) | K trades/fight (p90) | Co-active bars/fight (med) | Co-active bars/fight (p90) |
|:---|:-------|:--------------------|:--------------------|:-------------------|:-------------------|:-------------------------|:-------------------------|
| 2025_lychee | 181 | 191 | 710 | 161 | 1400 | 30 | 154 |
| 2026_collector | 100 | 154 | 561 | 1652 | 15238 | 50 | 175 |

### 6B — Fragmentation ratio

| Ratio | Definition | Value |
|:----|:---------|:----|
| Fragmentation ratio | median PM trades/fight (2026_collector) ÷ median PM trades/fight (2025_lychee) | 0.8063 |
| Note | Both eras API-sourced (data-api.polymarket.com); comparison valid |  |
| Stop-gate range | [0.4, 1.0] | PASS |

### 6C — MCGHOL detail (20260711 main card, known PM data gap)

20260711_MCGHOL | 394 PM trades | 380987 K trades | 8 co-active bars | 0.9% both
