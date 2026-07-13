# Exploratory log and pre-analysis plan
## Kalshi macro post-announcement drift; UFC price discovery

Frozen before any analysis is run. The sections marked FROZEN fix the test, windows,
kill criterion, and holdout, so that specification cannot be adjusted to the data after
the fact. Sections marked PLANNED record intent for later phases and are not yet binding;
each will be tightened into its own frozen section once the data it requires exists.

Date frozen: ____________   Git commit at freeze: ____________
Data snapshot: forward collector from 2026-05-04 onward; Lychee (Becker) dump archive.

---

## Track A — Macro post-announcement drift  (FROZEN, registered as a pilot)

Status. Underpowered by construction. The live window currently spans roughly 68 days,
giving only a handful of scheduled releases per series. Track A is therefore registered
as a pilot; the confirmatory reading is deferred until the event count grows through
ongoing collection.

Question. Following a scheduled macro release, does the Kalshi market-implied probability
continue to move in the direction of the initial repricing (continuation, or drift), or
is the post-release price already efficient, showing no continuation?

Series. KXCPIYOY, KXCPICOREYOY, KXFEDDECISION, KXFED, KXPAYROLLS, KXU3.

Event clock. t0 is the official release timestamp in UTC (BLS releases at 12:30 UTC for
CPI, payrolls and unemployment; the FOMC decision at 18:00 or 19:00 UTC depending on
daylight saving). A release calendar is stored at data/meta/macro_calendar.parquet and is
treated as fixed input.

Frozen specification.
- Jump is the change in the yes-price-implied probability over [t0, t0+5min].
- Drift is the change over (t0+5min, t0+Δ].
- Δ is frozen to the set {30, 60, 120} minutes. No other horizon is examined.
- Primary test: regression of Drift on Jump across events. Continuation corresponds to a
  positive, significant coefficient; efficiency corresponds to a coefficient
  indistinguishable from zero.
- Standard errors are clustered by release date.

Kill and stopping rule. While fewer than 20 events are available, the outcome is recorded
as inconclusive and revisited at N greater than or equal to 20, rather than shelved. Once
N reaches 20, if the drift coefficient's confidence interval contains zero at p above 0.10
across all frozen horizons, the drift hypothesis is shelved and not re-specified with
alternative windows.

Holdout. The single most recent release per series is sealed in data/holdout/ and scored
exactly once, after the specification is final.

Confounds logged in advance. Thin liquidity in the minutes around release; contract expiry
close to the event; overlapping releases on the same morning; and the March 2026
price-format change (integer cents in the Lychee history against fixed-point dollars in the
forward feed), which must be reconciled in data/meta before any pooling.

---

## Track B — UFC price discovery

Phase 1 is Kalshi-internal and well-powered, and is frozen now. Phase 2 is cross-venue,
requires data not yet held, and is recorded as intent only.

### Phase 1 — Within-venue order flow on KXUFCFIGHT  (FROZEN)

Data in hand: roughly 112 fights, about 224 fighter-markets, and 2.9 million trades
carrying taker_side.

Question. Within a KXUFCFIGHT market, does signed taker order-flow imbalance in one
interval predict the price revision in the following interval?

Frozen specification.
- Trades are bucketed into fixed 5-minute intervals in event-time within each
  fighter-market's active trading period.
- Order-flow imbalance in interval t is OFI(t) = (contracts with taker_side = yes) minus
  (contracts with taker_side = no).
- The response is the change in the last traded yes-price from interval t to interval t+1,
  the two intervals being non-overlapping.
- Primary test: regression of the interval-ahead price change on OFI(t) with fighter-market
  fixed effects. Predictive order flow corresponds to a positive, significant coefficient.
- Inference: standard errors clustered by fight, corroborated by a Romano-Wolf permutation
  test to guard against false positives.

Coverage floor (frozen). Only fighter-markets with at least 100 trades are included, and
the test requires at least 30 qualifying fights. If the floor is not met, the result is
reported as coverage-limited rather than as significant or null.

Kill and stopping rule. If the OFI coefficient's confidence interval contains zero at
p above 0.05 after the permutation check, the within-venue order-flow signal is shelved and
not re-specified with alternative bucket widths. The 5-minute bucket is the only width used
for the confirmatory test; any other width is exploratory and labelled as such.

Holdout. The two most recent fight cards are sealed in data/holdout/ and scored once.

### Phase 2 — Cross-venue lead-lag, Kalshi against Polymarket  (PLANNED, not yet binding)

To be frozen into its own section once forward orderbook collection and a cross-venue
market map exist. Intended test: an information-share (Hasbrouck) or Gonzalo-Granger
decomposition on aligned midprice series, with signed order flow on the leading venue as a
secondary predictor of the follower's revision.

Prerequisites: a Polymarket forward collector for trades and orderbook; Kalshi orderbook
collection; a common UTC clock with measured cross-venue skew; and a fighter-to-ticker map
joining Polymarket condition identifiers to KXUFCFIGHT tickers.

Confounds to log at that point: only a minority of nominally-matched cross-venue outcomes
are settlement-fungible, so settlement differences must be recorded per fight and not
mistaken for spreads; venue clock skew; the USDC-decimal against Kalshi-cent convention;
and the youth and liquidity asymmetry of Kalshi sports.

---

## Sequencing

The Track A pilot and Track B Phase 1 may be run in parallel now, since both rely only on
data already held. Phase 2 begins once the forward orderbook collectors have accumulated a
usable cross-venue sample. Nothing reads data/holdout/ until the relevant kill rule has been
cleared on the training data.
