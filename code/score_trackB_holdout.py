#!/usr/bin/env python3
"""ONE-SHOT holdout scoring for Track B Phase 1. Run once only. Do not iterate."""
import math, glob, sys
from pathlib import Path
import numpy as np
import pandas as pd

import re
sys.path.insert(0, "code")
from phase1_quintile_sort import bucketize, add_rolling_vol, add_ofi_variants, N_QUINTILES

_MON = {'JAN':'01','FEB':'02','MAR':'03','APR':'04','MAY':'05','JUN':'06',
        'JUL':'07','AUG':'08','SEP':'09','OCT':'10','NOV':'11','DEC':'12'}

def _card_date(t):
    m = re.search(r'KXUFCFIGHT-(\d{2})([A-Z]{3})(\d{2})', t)
    return f"20{m.group(1)}-{_MON.get(m.group(2),'00')}-{m.group(3)}" if m else "unknown"

RAW          = "data/raw/live"
SERIES       = "KXUFCFIGHT"
HOLDOUT_FILE = Path("data/holdout/trackB_phase1_holdout_fights.txt")
MIN_TRADES   = 100
OUT          = Path("qa/trackB_phase1_holdout_score.md")

def _fight_id(ticker): return ticker.rsplit("-", 1)[0]

def load_holdout():
    holdout = set(HOLDOUT_FILE.read_text().strip().splitlines())
    files = glob.glob(f"{RAW}/**/*.parquet", recursive=True)
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df = df.drop_duplicates("trade_id")
    df = df[df["ticker"].str.startswith(SERIES)].copy()
    df["created_time"] = pd.to_datetime(df["created_time"], utc=True, format="ISO8601")
    df["count"]     = pd.to_numeric(df["count_fp"],          errors="coerce")
    df["yes_price"] = pd.to_numeric(df["yes_price_dollars"], errors="coerce")
    df = df[df["taker_side"].isin(["yes","no"])].dropna(subset=["count","yes_price"])
    df["fight"] = df["ticker"].map(_fight_id)
    df["card"]  = df["ticker"].map(_card_date)
    df = df[df["fight"].isin(holdout)]
    tc   = df.groupby("ticker")["trade_id"].size()
    keep = tc[tc >= MIN_TRADES].index
    return df[df["ticker"].isin(keep)].sort_values("created_time").reset_index(drop=True)

def qsort_spread(b, ofi_col):
    v = b.dropna(subset=[ofi_col, "dp_1"]).copy()
    v["_q"] = pd.qcut(v[ofi_col], N_QUINTILES,
                      labels=[f"Q{i}" for i in range(1, N_QUINTILES+1)])
    cq   = v.groupby(["card","_q"], observed=True)["dp_1"].mean() * 100
    wide = cq.unstack("_q")[["Q1","Q5"]].dropna()
    spr  = wide["Q5"] - wide["Q1"]
    mu   = float(spr.mean())
    se   = float(spr.std(ddof=1)) / math.sqrt(len(spr)) if len(spr) > 1 else float("nan")
    t    = mu / se if se and not math.isnan(se) else float("nan")
    p    = math.erfc(abs(t) / math.sqrt(2)) if not math.isnan(t) else float("nan")
    return mu, se, t, p, int(len(spr))

# ---- run -----------------------------------------------------------------
print("Loading holdout ...", flush=True)
df = load_holdout()
print(f"  {len(df):,} trades | {df['ticker'].nunique()} markets | {df['fight'].nunique()} fights", flush=True)

print("Building bars ...", flush=True)
b = bucketize(df)
b = add_rolling_vol(b)
b = add_ofi_variants(b)

mu_z,   se_z,   t_z,   p_z,   nc_z   = qsort_spread(b, "ofi_z")
mu_vol, se_vol, t_vol, p_vol, nc_vol = qsort_spread(b, "ofi_vol")

confirmed = mu_z < 0 and mu_vol < 0
verdict   = "CONFIRMED" if confirmed else "NOT CONFIRMED"

lines = [
    "# Track B Phase 1 — Holdout Score",
    "",
    "**One-shot scoring per amended registration (commit 51711bc, 2026-07-13).**  ",
    "Confirmation criterion: both Q5-Q1 lag-1 spreads negative.  ",
    "No other holdout statistics computed.",
    "",
    f"Holdout: {df['fight'].nunique()} fights | {df['ticker'].nunique()} markets | {len(b):,} bars",
    "",
    "| OFI variant | Q5-Q1 lag-1 (ct) | SE | t | p | n_cards | Sign |",
    "|-------------|------------------|----|---|---|---------|------|",
    f"| z-OFI           | {mu_z:+.4f} | {se_z:.4f} | {t_z:+.2f} | {p_z:.4f} | {nc_z} | {'<0 checkmark' if mu_z < 0 else '>0 FAIL'} |",
    f"| volume-scaled   | {mu_vol:+.4f} | {se_vol:.4f} | {t_vol:+.2f} | {p_vol:.4f} | {nc_vol} | {'<0 checkmark' if mu_vol < 0 else '>0 FAIL'} |",
    "",
    f"## Verdict: {verdict}",
    "",
    f"z-OFI spread {'negative' if mu_z < 0 else 'positive'}, "
    f"volume-scaled spread {'negative' if mu_vol < 0 else 'positive'}. "
    f"{'Both negative: reversal signal confirmed out-of-sample.' if confirmed else 'Criterion not met.'}",
    "",
]

OUT.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print(f"Saved: {OUT}")
