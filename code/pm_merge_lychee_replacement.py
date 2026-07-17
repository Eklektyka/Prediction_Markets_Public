"""
pm_merge_lychee_replacement.py
===============================
Merge the API-sourced 2025 trades (pm_api_2025.parquet) with the existing
2026+ rows, replacing the Lychee complement-contaminated 2025 rows.

Archive step (runs FIRST, before any overwrite):
  data/interim/polymarket_ufc_trades.parquet
      -> data/raw/polymarket_ufc_trades_lychee_deprecated.parquet

The deprecated file is the reproducibility anchor for the contamination
analysis in qa/burn_filter_audit.md and qa/complement_fix_verification.md.

Merge logic:
  new interim = pm_api_2025.parquet   (185 crosswalk 2025 markets, API-sourced)
              + old interim rows with ts_utc.year >= 2026  (collector-sourced, untouched)

Schema note: pm_api_2025 has a different column set from the Lychee-derived rows.
Columns present only in Lychee rows (block_number, maker_asset_id, taker_asset_id,
maker_amount, taker_amount) are filled with NaN/empty in the API rows so the
combined file is schema-compatible with downstream scripts.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import shutil
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

REPO        = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
OLD_INTERIM = REPO / "data/interim/polymarket_ufc_trades.parquet"
API_2025    = REPO / "data/interim/pm_api_2025.parquet"
ARCHIVE     = REPO / "data/raw/polymarket_ufc_trades_lychee_deprecated.parquet"
NEW_INTERIM = OLD_INTERIM   # overwrite in place only AFTER archive confirmed


def main():
    print("=" * 72)
    print("pm_merge_lychee_replacement.py")
    print(f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 72)

    # Pre-flight checks
    if not OLD_INTERIM.exists():
        print(f"ERROR: {OLD_INTERIM} not found"); return
    if not API_2025.exists():
        print(f"ERROR: {API_2025} not found — run pm_gapfill_crosswalk.py first"); return
    if ARCHIVE.exists():
        print(f"WARNING: archive already exists at {ARCHIVE}")
        print("  This means the merge has already run once.")
        print("  Refusing to overwrite the archive. Exiting.")
        return

    # ── Step 1: ARCHIVE old interim (rename, not copy) ────────────────────
    print(f"\n[1] Archiving old interim file ...")
    print(f"  {OLD_INTERIM.name}")
    print(f"    -> data/raw/{ARCHIVE.name}")
    shutil.move(str(OLD_INTERIM), str(ARCHIVE))
    print(f"  Done. Archive size: {ARCHIVE.stat().st_size / 1e6:.1f} MB")

    # ── Step 2: Load archived file, keep only 2026+ rows ─────────────────
    print(f"\n[2] Loading 2026+ rows from archive ...")
    old = pd.read_parquet(ARCHIVE)
    old["ts_utc"] = pd.to_datetime(old["ts_utc"], utc=True)
    mask_2026 = old["ts_utc"].dt.year >= 2026
    df_2026   = old[mask_2026].copy()
    df_lychee_2025_count = (~mask_2026).sum()
    print(f"  Archive total rows:   {len(old):,}")
    print(f"  Lychee 2025 rows:     {df_lychee_2025_count:,}  (dropped)")
    print(f"  2026+ rows retained:  {len(df_2026):,}")

    # ── Step 3: Load API 2025 replacement ─────────────────────────────────
    print(f"\n[3] Loading API 2025 replacement ...")
    df_api = pd.read_parquet(API_2025)
    df_api["ts_utc"]    = pd.to_datetime(df_api["ts_utc"], utc=True)
    df_api["market_id"] = df_api["market_id"].astype(str)
    print(f"  API 2025 rows:   {len(df_api):,}")
    print(f"  Markets:         {df_api['market_id'].nunique()}")
    print(f"  Date range:      {df_api['ts_utc'].min().strftime('%Y-%m-%d')} -> "
          f"{df_api['ts_utc'].max().strftime('%Y-%m-%d')}")

    # ── Step 4: Schema alignment ──────────────────────────────────────────
    # Add Lychee-only columns to API rows as NaN so concat works cleanly.
    # Downstream scripts that compute usdc_amount from maker/taker amounts
    # should prefer the usdc_amount column already present in API rows.
    print(f"\n[4] Aligning schemas ...")
    lychee_only_cols = ["block_number", "maker_asset_id", "taker_asset_id",
                        "maker_amount", "taker_amount"]
    for col in lychee_only_cols:
        if col not in df_api.columns:
            df_api[col] = np.nan
    # Add API-only columns to 2026 rows as NaN
    api_only_cols = ["size", "usdc_amount", "outcome", "taker_side",
                     "condition_id", "tx_hash", "proxy_wallet"]
    for col in api_only_cols:
        if col not in df_2026.columns:
            df_2026[col] = np.nan

    # Ensure shared columns have compatible types
    df_api["market_id"]  = df_api["market_id"].astype(str)
    df_2026["market_id"] = df_2026["market_id"].astype(str)

    # ── Step 5: Concatenate and write ─────────────────────────────────────
    print(f"\n[5] Concatenating and writing new interim ...")
    combined = pd.concat([df_api, df_2026], ignore_index=True)
    combined = combined.sort_values("ts_utc").reset_index(drop=True)

    combined.to_parquet(NEW_INTERIM, index=False)

    print(f"\n  {'Before':>10}  {'After':>10}")
    print(f"  {'----------':>10}  {'----------':>10}")
    print(f"  {df_lychee_2025_count + len(df_2026):>10,}  {len(combined):>10,}  total rows")
    print(f"  {df_lychee_2025_count:>10,}  {len(df_api):>10,}  2025-era rows")
    print(f"  {len(df_2026):>10,}  {len(df_2026):>10,}  2026+ rows (unchanged)")
    print(f"\n  Saved: {NEW_INTERIM}")
    print(f"  Archive: {ARCHIVE}")
    print(f"\n  Downstream panels NOT rebuilt. Run panel scripts to propagate.")


if __name__ == "__main__":
    main()
