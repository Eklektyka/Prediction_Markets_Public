# Hygiene Block 1 — Crosswalk & Price Heuristic Verification
**Generated:** 2026-07-14 10:58 UTC
**Mode:** Read-only. No upstream files modified.

---

## Check (a) — SPIGAZ REMAP

The override in `data/meta/crosswalk_overrides.csv` remapped `20251122_SPIGAZ` from the
wrong market (Cortes-Acosta/Gaziev, pm=695777, slug=`ufc-wal2-sha27-2025-11-22`) to the
correct market (Spivac/Gaziev, pm=690296, slug=`ufc-ser2-sha27-2025-11-22`).

| Field | Expected | Actual | Match |
|:------|:---------|:-------|:-----:|
| pm_id | `690296` | `690296` | YES |
| pm_slug | `ufc-ser2-sha27-2025-11-22` | `ufc-ser2-sha27-2025-11-22` | YES |
| Not wrong market (695777) | True | True | YES |
| match_confidence | exact | exact | YES |
| fighters_pm | Spivac / Gaziev | ["Spivac", "Gaziev"] | OK |

**Panel validation:**
- Co-active bars: 54
- MAD (K_last − PM_last on co-active bars): 4.80 cents — within expected range; override propagated correctly.

**Verdict (a): PASS**

---

## Check (b) — Maker-side USDC heuristic

**Heuristic:** `usdc_amount = maker_amount if len(maker_asset_id) < 20 else taker_amount`

**Ground truth:** In the Polymarket CTF CLOB, USDC (collateral) is stored as asset ID `"0"`
(string length 1). Outcome tokens are 256-bit integers in decimal form (73–78 chars).
Reference: `fpmm_collateral_lookup.json` confirms USDC on Polygon =
`0x5FaB5764f263c5CE93424F8c45e46A742Cc5C8d6`, which maps to CTF ID `"0"`.

**Asset ID distribution in `polymarket_ufc_trades.parquet` (533,209 rows):**

| maker_asset_id length | Count | Values |
|:---------------------:|------:|:-------|
| 1 (USDC = "0") | 453,056 | `"0"` |
| 73–78 (outcome tokens) | 80,153 | 78-char decimal token IDs |
| 2–19 (ambiguous zone) | 0 | (none) |

- Unique short maker IDs: `{'0'}`
- Unique short taker IDs: `{'0'}`
- Disagreement (heuristic ≠ ground truth): **0 rows (0.0000%)**
- Impossible trades (both sides USDC or both tokens): 0 / 0

The heuristic `len < 20` is mathematically equivalent to `asset_id == "0"` on this dataset
because the only values with length < 20 are `"0"` itself, and all `"0"` values have length 1.
No assets exist in the 2–19 char range that could be misclassified.

**Verdict (b): PASS — STOP**
The heuristic is validated. No price impact. No rebuild required.

---

## Summary

| Check | Result |
|:------|:-------|
| (a) SPIGAZ REMAP landed | **PASS** — pm_id=690296, MAD=4.80c |
| (b) USDC heuristic | **PASS — STOP** — 0 disagreements on 533,209 trades |
