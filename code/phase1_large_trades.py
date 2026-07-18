#!/usr/bin/env python3
"""Large-trade OFI quintile sort. Run from repo root."""
import math, sys
import numpy as np
import pandas as pd
sys.path.insert(0, "code")
from phase1_quintile_sort import load_training, N_QUINTILES

BUCKET = "5min"
OUT    = "qa/phase1_large_trades.md"

def build_panel(df, ofi_col_name, large_mask_col):
    df2 = df.copy()
    df2["signed_large"] = np.where(
        df2[large_mask_col],
        np.where(df2["taker_side"] == "yes",  df2["count"], -df2["count"]),
        0.0
    )
    df2["bucket"] = df2["created_time"].dt.floor(BUCKET)
    b = (df2.groupby(["fight","card","ticker","bucket"])
           .agg(ofi_large  = ("signed_large", "sum"),
                last_price = ("yes_price",    "last"))
           .reset_index()
           .sort_values(["ticker","bucket"])
           .reset_index(drop=True))
    lp = b.groupby("ticker")["last_price"]
    b["dp_1"] = lp.shift(-1) - b["last_price"]
    # z-score within market
    stats = b.groupby("ticker")["ofi_large"].agg(mu="mean", sd="std")
    b = b.join(stats, on="ticker")
    b["ofi_z"] = (b["ofi_large"] - b["mu"]) / b["sd"].replace(0.0, np.nan)
    return b.dropna(subset=["ofi_z","dp_1"])

def qsort(b):
    if b.empty or b["ofi_z"].nunique() < N_QUINTILES:
        return None, None
    b = b.copy()
    b["_q"] = pd.qcut(b["ofi_z"], N_QUINTILES,
                      labels=[f"Q{i}" for i in range(1, N_QUINTILES+1)])
    qdf = b.groupby("_q", observed=True).agg(
        ofi_z_mean = ("ofi_z", "mean"),
        dp1_ct     = ("dp_1",  lambda x: x.mean() * 100),
        n          = ("ofi_z", "size"),
    )
    # Q5-Q1 spread clustered by fight card
    cq   = b.groupby(["card","_q"], observed=True)["dp_1"].mean() * 100
    wide = cq.unstack("_q")[["Q1","Q5"]].dropna()
    spr  = wide["Q5"] - wide["Q1"]
    mu   = float(spr.mean())
    se   = float(spr.std(ddof=1)) / math.sqrt(len(spr))
    t    = mu / se
    p    = math.erfc(abs(t) / math.sqrt(2))
    return qdf, dict(spread=mu, se=se, t=t, p=p, n_cards=len(spr))

# ---- main ----------------------------------------------------------------
print("Loading ...", flush=True)
df = load_training()

# large-trade flag: top decile of count within each market
p90 = df.groupby("ticker")["count"].quantile(0.90).rename("p90")
df  = df.join(p90, on="ticker")
df["is_large"] = df["count"] >= df["p90"]

print("Building large-trade panel ...", flush=True)
b_large = build_panel(df, "ofi_large", "is_large")

print("Building block-trade panel ...", flush=True)
df["is_block"] = df["is_block_trade"].astype(bool)
b_block = build_panel(df, "ofi_block", "is_block")

qdf_l, s_l = qsort(b_large)
qdf_b, s_b = qsort(b_block)

# ---- markdown ------------------------------------------------------------
lines = [
    "## Large-Trade OFI Quintile Sort (lag-1 forward return)",
    "",
    "**Large trades:** top-decile of `count` within each market (pre-event training trades).",
    "OFI = signed large-trade volume per 5-min bar, z-scored within market.",
    "Forward return = close(t+1) - close(t), in cents.",
    "Q5-Q1 SE clustered by fight card.",
    "",
    "| quintile | mean z-OFI | dp_lag1 (ct) | n_bars |",
    "|----------|-----------|--------------|--------|",
]
for q, row in qdf_l.iterrows():
    lines.append(f"| {q} | {row['ofi_z_mean']:+.4f} | {row['dp1_ct']:+.4f} | {int(row['n']):,} |")

block_line = (
    f"**Block trades only** (`is_block_trade==True`): "
    f"Q5-Q1 = {s_b['spread']:+.4f} ct "
    f"| SE: {s_b['se']:.4f} | t: {s_b['t']:+.2f} | p: {s_b['p']:.4f} "
    f"| n_cards: {s_b['n_cards']} | n_bars: {len(b_block):,}"
    if s_b is not None
    else f"**Block trades only** (`is_block_trade==True`): "
         f"no block trades in training set (n_bars with non-zero large-block OFI = "
         f"{(df['is_block']).sum():,}); sort not applicable."
)

lines += [
    "",
    f"**Q5-Q1 (large-trade OFI): {s_l['spread']:+.4f} ct** "
    f"| SE: {s_l['se']:.4f} | t: {s_l['t']:+.2f} | p: {s_l['p']:.4f} "
    f"| n_cards: {s_l['n_cards']}",
    "",
    block_line,
    "",
]

# comparison sentence
sign = "same direction as" if s_l["spread"] < 0 else "opposite direction from"
lines.append(
    f"Large-trade Q5-Q1 = {s_l['spread']:+.4f} ct vs all-trade Q5-Q1 = -0.12 ct "
    f"({sign} the all-trade result; "
    f"magnitude ratio {abs(s_l['spread']/0.12):.2f}x)."
)
lines.append("")

with open(OUT, "a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"Saved: {OUT}")
