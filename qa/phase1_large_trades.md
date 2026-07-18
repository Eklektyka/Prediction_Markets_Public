## Large-Trade OFI Quintile Sort (lag-1 forward return)

**Large trades:** top-decile of `count` within each market (pre-event training trades).
OFI = signed large-trade volume per 5-min bar, z-scored within market.
Forward return = close(t+1) - close(t), in cents.
Q5-Q1 SE clustered by fight card.

| quintile | mean z-OFI | dp_lag1 (ct) | n_bars |
|----------|-----------|--------------|--------|
| Q1 | -0.2016 | +0.0207 | 24,274 |
| Q2 | -0.1207 | -0.0045 | 23,992 |
| Q3 | -0.0930 | -0.0098 | 24,469 |
| Q4 | -0.0666 | -0.0033 | 24,312 |
| Q5 | +0.4959 | -0.0155 | 23,604 |

**Q5-Q1 (large-trade OFI): -0.0811 ct** | SE: 0.0334 | t: -2.43 | p: 0.0152 | n_cards: 8

**Block trades only** (`is_block_trade==True`): no block trades in training set (n_bars with non-zero large-block OFI = 0); sort not applicable.

Large-trade Q5-Q1 = -0.0811 ct vs all-trade Q5-Q1 = -0.12 ct (same direction as the all-trade result; magnitude ratio 0.68x).

