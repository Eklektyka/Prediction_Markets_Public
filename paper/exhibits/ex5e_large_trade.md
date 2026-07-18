# Exhibit 5E — Large-Trade OFI Split (Post-Hoc Descriptive, 26-Card Confirmatory Panel)
**Generated:** 2026-07-18 17:36 UTC
**Script:** `code/ex5e_large_trade.py`
**Panel:** 26 fight cards, Feb–Nov 2025, 5-min bars, [5,95]¢ price filter, card-clustered SE.
**Prior vintage commit:** bb5d695

---

## (a) POST-HOC Label

This analysis is **NOT part of the registered confirmatory test.** It is a post-hoc descriptive cut applying the pre-specified large-trade filter (defined in `qa/phase1_large_trades.md`) to the confirmatory panel. Results are reported for context only and should not be interpreted as confirming or rejecting any pre-registered hypothesis.

---

## (b) Vintage Check

**Command:** `git diff bb5d695 -- code/trackB_phase1_orderflow.py code/phase1_quintile_sort.py code/score_trackB_holdout.py data/interim/lychee_macro_trades.parquet`

**Result:** No diff. No relevant OFI pipeline file changed since bb5d695. Proceeding to checksum.

**Commit 5afccf3:** Added files only (code/ex5d_diagnostics.py, paper/exhibits/ex5d_diagnostics.md) — no modification to existing files. Confirmed.

---

## (c) Checksum Reproduction

Same confirmatory panel as ex5/ex5d.

| Metric | Reproduced | Expected | Verdict |
|:-------|----------:|--------:|:--------|
| vol-OFI Q5-Q1 lag-1 (ct) | -1.1265 | −1.1265 | PASS |
| t-statistic (vol-OFI) | -6.29 | −6.29 | PASS |
| n_bars | 62,119 | 62,119 | PASS |
| n_cards | 26 | 26 | PASS |

**Checksum status: PASS**

z-OFI cross-check (not in checksum gate but reported):
vol-OFI = -1.1265 ct, z-OFI = -0.1356 ct (all-trade).

---

## (d) Large-Trade Cut-Off Definition (verbatim from qa/phase1_large_trades.md)

> **Large trades:** top-decile of `count` within each market (pre-event training trades).
> OFI = signed large-trade volume per 5-min bar, z-scored within market.

Applied here to the confirmatory panel (post-hoc): p90 of `count` computed per ticker within the Feb–Nov 2025 confirmatory sample. `is_large = (count >= p90 within ticker)`.

---

## (e) Quintile Sort Results: Large-Trade OFI Only

Note: For vol-OFI, 2 of 5 requested bins were formed (many bars have zero large-trade flow; duplicate bin edges dropped — see E5e-E). Q1 = lowest bin, Q5 = highest bin. Bins Q2–Q4 do not exist and show NaN.

### Volume-Scaled (primary): large-trade OFI / rolling 6-hour volume

Bins formed: 2 (of 5 requested)

| Quintile | Mean ofi_large_vol | Mean dp_lag1 (cents) |
|:--------:|:------------------:|:--------------------:|
| Q1 | -0.0049 | -0.0349 |
| Q2 | nan | +nan |
| Q3 | nan | +nan |
| Q4 | nan | +nan |
| Q5 | 0.1402 | -0.0084 |

**Q5-Q1 spread:** +0.1350 ct | SE: 0.0741 | t: +1.82 | p: 0.0686 | n_cards: 26 | n_bars: 62,119

### z-OFI (secondary): large-trade OFI z-scored within market

Bins formed: 5 (of 5 requested)

| Quintile | Mean ofi_large_z | Mean dp_lag1 (cents) |
|:--------:|:----------------:|:--------------------:|
| Q1 | -0.4352 | -0.0067 |
| Q2 | -0.2178 | -0.0465 |
| Q3 | -0.1612 | -0.0475 |
| Q4 | -0.0884 | -0.0313 |
| Q5 | 0.9048 | -0.0177 |

**Q5-Q1 spread:** +0.0532 ct | SE: 0.0769 | t: +0.69 | p: 0.4892 | n_cards: 26 | n_bars: 62,119

---

## (f) Side-by-Side: Large-Trade vs All-Trade

| Variant | All-Trade Q5-Q1 (ct) | Large-Trade Q5-Q1 (ct) | t | p | Ratio (large/all) |
|:--------|:--------------------:|:----------------------:|:---:|:---:|:-----------------:|
| vol-OFI (primary) | −1.1265 | +0.1350 | +1.82 | 0.0686 | 0.12× |
| z-OFI (secondary) | −0.1356 | +0.0532 | +0.69 | 0.4892 | 0.39× |

**Historical context (8-card training, exploratory):** z-OFI = −0.081 ct, ratio = 0.68×.

---

## (g) Documented Ambiguities

| ID | Ambiguity | Choice Made |
|:---|:----------|:------------|
| E5e-A | Training vs confirmatory panel for p90 threshold | p90 computed within confirmatory panel (same trades used for analysis). The original spec says "pre-event training trades" but the confirmatory panel is the analysis universe here. This is a post-hoc descriptive so no pre-registration conflict. |
| E5e-B | Denominator for large-trade vol-OFI | Rolling 6-hour volume = total_count (all trades, not just large), same as all-trade vol-OFI denominator. This makes the vol-OFI variants directly comparable. |
| E5e-C | z-OFI markets excluded | Markets where large-trade ofi_sd = 0 have large_z = NaN and are excluded from the z-OFI sort. n_bars may differ between variants. |
| E5e-D | is_large definition | count >= p90 (inclusive), consistent with phase1_large_trades.py line: `df["is_large"] = df["count"] >= df["p90"]` |
| E5e-E | Duplicate bin edges in large-trade vol-OFI quintile sort | Many 5-min bars contain zero large-trade flow (no large trade occurred in that bar). For vol-OFI this creates many tied zero values and only 2 distinct bins can be formed. `pd.qcut` is called with `duplicates='drop'`; the lowest bin is labelled Q1 and the highest Q5. Q2-Q4 are absent. The Q5-Q1 spread is therefore a 2-category comparison (most-negative-flow bars vs most-positive-flow bars), not a full quintile sort. For z-OFI, 5 bins form because z-scoring distributes the zeros across multiple bins. |
