#!/usr/bin/env python3
"""Build and save the Track B 5-min bar panel. Run from repo root."""
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, "code")
from phase1_quintile_sort import load_training, bucketize, add_rolling_vol, add_ofi_variants

BUCKET  = "5min"
OUT     = "data/clean/trackB_bars_5min.parquet"

print("Loading ...", flush=True)
df = load_training()

# large-trade flag: top decile of count within each market
p90 = df.groupby("ticker")["count"].quantile(0.90).rename("p90")
df  = df.join(p90, on="ticker")
df["is_large"] = df["count"] >= df["p90"]
df["signed_large"] = np.where(df["is_large"],
    np.where(df["taker_side"] == "yes", df["count"], -df["count"]), 0.0)

print("Bucketizing ...", flush=True)
b = bucketize(df)

# large-trade OFI per bar
large_agg = (df.assign(bucket=df["created_time"].dt.floor(BUCKET))
               .groupby(["ticker","bucket"])["signed_large"].sum()
               .rename("ofi_large"))
b = b.join(large_agg, on=["ticker","bucket"])
b["ofi_large"] = b["ofi_large"].fillna(0.0)

print("Rolling volume + OFI variants ...", flush=True)
b = add_rolling_vol(b)
b = add_ofi_variants(b)

# large-trade z-OFI
stats_l = b.groupby("ticker")["ofi_large"].agg(mu="mean", sd="std")
b = b.join(stats_l, on="ticker")
b["ofi_large_z"] = (b["ofi_large"] - b["mu"]) / b["sd"].replace(0.0, np.nan)
b = b.drop(columns=["mu","sd"])

# forward returns in cents
b["dp_1_ct"] = b["dp_1"] * 100
b["dp_2_ct"] = b["dp_2"] * 100
b["dp_contemp_ct"] = b["dp_contemp"] * 100

b.to_parquet(OUT, index=False)
print(f"\nRows : {len(b):,}")
print(f"Cols : {list(b.columns)}")
print(f"Saved: {OUT}")
