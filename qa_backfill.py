#!/usr/bin/env python3
"""qa_backfill.py — quick census of what the backfill landed. Run from repo root."""
import glob, pandas as pd
from pathlib import Path

files = glob.glob("data/raw/live/**/*.parquet", recursive=True)
if not files:
    raise SystemExit("No parquet files under data/raw/live — did the backfill run?")

df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
df["created_time"] = pd.to_datetime(df["created_time"], utc=True)

# derive a series label from the ticker prefix (everything before the first '-')
df["series"] = df["ticker"].str.split("-").str[0]

print(f"parquet files on disk : {len(files)}")
print(f"total trades          : {len(df):,}")
print(f"unique markets         : {df['ticker'].nunique():,}")
print(f"date range (UTC)       : {df['created_time'].min()}  ->  {df['created_time'].max()}")
print(f"taker_side present     : {'taker_side' in df.columns}")
print("\ntrades by series:")
print(df.groupby("series").agg(trades=("trade_id", "size"),
                               markets=("ticker", "nunique"),
                               first=("created_time", "min"),
                               last=("created_time", "max")).to_string())

# save a coverage snapshot for the record
out = Path("qa/backfill_coverage.csv")
df.groupby("series").agg(trades=("trade_id", "size"),
                         markets=("ticker", "nunique"),
                         first=("created_time", "min"),
                         last=("created_time", "max")).to_csv(out)
print(f"\nsaved -> {out}")
