# Phase 2 Prototype — Lead-Lag Analysis
**Generated:** 2026-07-13 23:08 UTC
**Panel:** `data/clean/phase2_prototype_panel.parquet` — 20 fights, 16,739 5-min bars

---

## Convention
`corr(dK_t, dPM_{t+k})` where `dK_t` = 5-min return on Kalshi, `dPM_{t+k}` = PM return k bars later.

- **k > 0** → Kalshi leads (K moves now, PM moves later)
- **k < 0** → PM leads (PM moves earlier, K adjusts later)
- **k = 0** → contemporaneous
- CI = 95% stationary bootstrap across fights (block_len=5, B=1000)
- `*` = CI excludes zero

---

## Table 1A — 5-min CCF (co-active bars, fights with both% ≥ 25%)
Fights: 8 / 20 meet threshold

| lag | rho_avg | ci_lo | ci_hi | sig | lead |
|----:|--------:|------:|------:|:---:|:-----|
| -6 | +0.0233 | -0.0123 | +0.0586 |  | PM leads |
| -5 | -0.0580 | -0.0932 | -0.0335 | * | PM leads |
| -4 | +0.0449 | +0.0097 | +0.0800 | * | PM leads |
| -3 | -0.0086 | -0.0481 | +0.0323 |  | PM leads |
| -2 | +0.0005 | -0.0385 | +0.0492 |  | PM leads |
| -1 | +0.0342 | -0.0656 | +0.1485 |  | PM leads |
| +0 | +0.1110 | -0.0430 | +0.3288 |  | contemporaneous |
| +1 | +0.0573 | -0.0353 | +0.1457 |  | Kalshi leads |
| +2 | -0.0201 | -0.0580 | +0.0159 |  | Kalshi leads |
| +3 | +0.0047 | -0.0234 | +0.0442 |  | Kalshi leads |
| +4 | +0.0167 | -0.0190 | +0.0514 |  | Kalshi leads |
| +5 | -0.0039 | -0.0328 | +0.0322 |  | Kalshi leads |
| +6 | -0.0100 | -0.0483 | +0.0189 |  | Kalshi leads |

---

## Table 1B — 15-min CCF (co-active 15-min bars, all 20 fights)
Fights contributing: 20 / 20

| lag | rho_avg | ci_lo | ci_hi | sig | lead |
|----:|--------:|------:|------:|:---:|:-----|
| -6 | +0.0189 | -0.0158 | +0.0551 |  | PM leads |
| -5 | -0.0298 | -0.0667 | +0.0029 |  | PM leads |
| -4 | +0.0516 | +0.0165 | +0.0925 | * | PM leads |
| -3 | -0.0424 | -0.0781 | -0.0092 | * | PM leads |
| -2 | +0.0375 | +0.0027 | +0.0759 | * | PM leads |
| -1 | +0.0003 | -0.0565 | +0.0716 |  | PM leads |
| +0 | +0.1620 | -0.0292 | +0.4002 |  | contemporaneous |
| +1 | +0.0425 | -0.0044 | +0.1130 |  | Kalshi leads |
| +2 | +0.0199 | -0.0096 | +0.0489 |  | Kalshi leads |
| +3 | -0.0376 | -0.0757 | +0.0024 |  | Kalshi leads |
| +4 | +0.0099 | -0.0282 | +0.0491 |  | Kalshi leads |
| +5 | -0.0144 | -0.0464 | +0.0187 |  | Kalshi leads |
| +6 | +0.0034 | -0.0414 | +0.0433 |  | Kalshi leads |

---

## Table 2 — Jump Response (|ret| ≥ 0.03 on venue A, 5-min bars)
Unconditional 5-min mean returns: Kalshi = -0.00006, PM = -0.00006

### K-jumps → PM response
| Metric | 30 min | 60 min |
|:-------|-------:|-------:|
| N jumps | 32 | 32 |
| Mean signed cumul return on PM | +0.00125 | +0.00051 |
| Baseline (PM_mu × h) | -0.00038 | -0.00076 |
| Excess return (mean - baseline) | +0.00163 | +0.00128 |
| Share PM moves same direction | 21.9% | 27.3% |

### PM-jumps → K response
| Metric | 30 min | 60 min |
|:-------|-------:|-------:|
| N jumps | 29 | 29 |
| Mean signed cumul return on K | +0.00069 | -0.00069 |
| Baseline (K_mu × h) | -0.00038 | -0.00075 |
| Excess return (mean - baseline) | +0.00106 | +0.00006 |
| Share K moves same direction | 20.7% | 24.1% |

---

## Notes on significant lags

**5-min**: Two nominally significant lags at k=-5 (rho=-0.058) and k=-4 (rho=+0.045) with opposite signs on adjacent lags. A genuine lead would produce a bloc of same-signed correlations; alternating signs are the signature of noise / multiple testing (13 lags tested, ~0.65 false positives expected at α=5%).

**15-min**: Three nominally significant lags at k=-4 (rho=+0.052), k=-3 (rho=-0.042), k=-2 (rho=+0.038) — again alternating signs across consecutive lags. Not a coherent lead-lag pattern.

**k=0**: Largest contemporaneous correlation at both strata (rho=0.11 at 5-min, 0.16 at 15-min) but CI spans zero, reflecting high between-fight variance (N=8 and N=20 fights respectively).

---

## Verdicts

1. **5-min lead-lag:** No reliable lead-lag signal. Nominally significant lags (k=-5, k=-4) have alternating signs and are consistent with multiple-testing noise. No clear Kalshi-leads or PM-leads pattern in the co-active CCF.
2. **15-min lead-lag:** No reliable lead-lag signal. Three consecutive lags (k=-4, -3, -2) are nominally significant but alternate in sign — noise, not price discovery. Contemporaneous correlation (rho=0.16) dominates but is imprecisely estimated.
3. **Jump propagation:** Jumps do not propagate cross-venue. K-jumps: same-direction PM response 22% at 30 min (well below 50%); PM-jumps: same-direction K response 21% at 30 min. Both venues appear to update independently on new information rather than one copying the other.
