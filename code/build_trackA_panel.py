"""
code/build_trackA_panel.py
==========================
Builds data/clean/trackA_event_panel.parquet.

Sources
  Primary  : data/raw/live/          (collector, date-partitioned parquet)
  Secondary: data/interim/lychee_macro_trades.parquet
             (Becker/Lychee dump filtered to macro tickers; schema-normalised
              here: yes_price [cents 0-100] -> yes_price_dollars [0-1 float])
Deduplication on trade_id across sources.

Contract selection
  For each macro event t0, load ALL macro-series tickers visible in the window.
  Keep only tickers whose inferred expiry is >72h after t0.
  Drop contracts settled by the print itself (expiry <= t0+72h).
  Expiry inferred from macro_calendar.parquet; fallback to mid-month approximation.

Per (event × market) columns
  event_series, release_name, release_time_utc,
  ticker, contract_series, contract_month, expiry_utc, expiry_lag_h,
  pre_price, price_30m, price_4h, price_24h,
  pre_trade_count, post_30m_count, post_4h_count, post_24h_count,
  stale_30m_min, stale_4h_min, stale_24h_min,
  usable  (True if pre_trade_count>=1 AND post_24h_count>=1)

Prints: events with >=1 usable market, total usable rows, attrition table by series.
"""

import os, sys, warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO            = "C:/Users/micha/OneDrive/Pulpit/Kalshi/Prediction_Markets_Public"
LIVE_DIR        = f"{REPO}/data/raw/live"
LYCHEE_FLAT     = f"{REPO}/data/interim/lychee_macro_trades.parquet"
CAL_PATH        = f"{REPO}/data/meta/macro_calendar.parquet"
OUT_PATH        = f"{REPO}/data/clean/trackA_event_panel.parquet"

MACRO_SERIES    = {"KXCPIYOY", "KXCPICOREYOY", "KXFEDDECISION", "KXFED", "KXPAYROLLS", "KXU3"}
PRE_LOOKBACK_H  = 6
EXPIRY_THRESH_H = 72

_MONTH_TO_NUM = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
_NUM_TO_ABB = {v: k[:3].upper() for k, v in _MONTH_TO_NUM.items()}


# ── helpers ────────────────────────────────────────────────────────────────────

def release_name_to_month_code(name):
    """'Employment Situation April 2026' -> '26APR'."""
    words = name.split()
    try:
        yr2   = words[-1][2:]          # '26'
        month = _MONTH_TO_NUM[words[-2]]
        return f"{yr2}{_NUM_TO_ABB[month]}"
    except (KeyError, IndexError):
        return None


def month_code_to_ts_approx(code):
    """'27APR' -> Timestamp for rough expiry when not in calendar (far-future contracts)."""
    try:
        yr  = int("20" + code[:2])
        mon = {v: k for k, v in _NUM_TO_ABB.items()}[code[2:]]
        return pd.Timestamp(yr, mon, 15, tz="UTC")
    except Exception:
        return None


def build_expiry_map(cal):
    """(contract_series, month_code) -> release_time_utc."""
    em = {}
    for _, row in cal.iterrows():
        code = release_name_to_month_code(row["release_name"])
        if code:
            em[(row["series"], code)] = row["release_time_utc"]
    return em


def load_date(base_dir, date_str):
    """Load all macro-series parquet files for one date partition. Returns DataFrame or None."""
    folder = os.path.join(base_dir, f"date={date_str}")
    if not os.path.isdir(folder):
        return None
    frames = []
    for fname in os.listdir(folder):
        if not fname.endswith(".parquet"):
            continue
        try:
            df = pd.read_parquet(os.path.join(folder, fname))
            mask = df["ticker"].str.split("-").str[0].isin(MACRO_SERIES)
            sub  = df[mask]
            if not sub.empty:
                frames.append(sub)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else None


def last_price_at(grp_sorted, t):
    """Last yes_price_dollars at or before t. Returns (price, stale_min) or (nan, nan)."""
    sub = grp_sorted[grp_sorted["created_time"] <= t]
    if sub.empty:
        return np.nan, np.nan
    last = sub.iloc[-1]
    stale = (t - last["created_time"]).total_seconds() / 60.0
    return float(last["yes_price_dollars"]), round(stale, 1)


def count_in(grp_sorted, t_lo, t_hi, inclusive_lo=False):
    """Count trades in (t_lo, t_hi] or [t_lo, t_hi)."""
    if inclusive_lo:
        mask = (grp_sorted["created_time"] >= t_lo) & (grp_sorted["created_time"] < t_hi)
    else:
        mask = (grp_sorted["created_time"] > t_lo) & (grp_sorted["created_time"] <= t_hi)
    return int(mask.sum())


# ── 1. Calendar ────────────────────────────────────────────────────────────────
cal = pd.read_parquet(CAL_PATH)
cal["release_time_utc"] = pd.to_datetime(cal["release_time_utc"], utc=True)
expiry_map = build_expiry_map(cal)

# Events that have already occurred (live data may cover them)
today    = pd.Timestamp.now(tz="UTC")
cal_past = cal[cal["release_time_utc"] < today].copy()

# Unique event timestamps with their primary series for labelling
event_meta = (
    cal_past
    .sort_values("release_time_utc")
    .groupby("release_time_utc", sort=False)
    .agg(event_series=("series", "first"), release_name=("release_name", "first"))
    .reset_index()
)

# ── 2. Collect all needed date strings ────────────────────────────────────────
from datetime import timedelta as _td

needed_dates = set()
for t0 in event_meta["release_time_utc"]:
    t_pre  = t0 - pd.Timedelta(hours=PRE_LOOKBACK_H)
    t_post = t0 + pd.Timedelta(hours=24)
    cur = t_pre.date()
    end = t_post.date()
    while cur <= end:
        needed_dates.add(str(cur))
        cur += _td(days=1)

# ── 3. Pre-load lychee flat parquet and index by date ─────────────────────────
# Schema normalisation: yes_price (cents int) -> yes_price_dollars (float 0-1)
lychee_by_date = {}   # date_str -> DataFrame (collector-compatible schema)
if os.path.exists(LYCHEE_FLAT):
    _lychee = pd.read_parquet(LYCHEE_FLAT,
                               columns=["trade_id", "ticker", "yes_price", "created_time"])
    _lychee["yes_price_dollars"] = pd.to_numeric(_lychee["yes_price"], errors="coerce") / 100.0
    _lychee["created_time"]      = pd.to_datetime(_lychee["created_time"], utc=True)
    _lychee = _lychee.dropna(subset=["yes_price_dollars", "created_time"])
    for _ds, _grp in _lychee.groupby(_lychee["created_time"].dt.date.astype(str)):
        lychee_by_date[_ds] = _grp.reset_index(drop=True)
    print(f"Lychee flat: {len(_lychee):,} rows across {len(lychee_by_date)} dates loaded.")
else:
    print(f"Lychee flat not found at {LYCHEE_FLAT} — using live only.")

# ── 4. Load & cache all needed dates (live + lychee, deduped on trade_id) ─────
date_cache = {}   # date_str -> DataFrame
lychee_dates_found = 0

for ds in sorted(needed_dates):
    frames = []
    live_df   = load_date(LIVE_DIR, ds)
    if live_df is not None:
        frames.append(live_df)
    if ds in lychee_by_date:
        frames.append(lychee_by_date[ds])
        lychee_dates_found += 1
    if not frames:
        continue
    combined = pd.concat(frames, ignore_index=True)
    combined  = combined.drop_duplicates(subset=["trade_id"])
    combined["created_time"]      = pd.to_datetime(combined["created_time"], utc=True)
    combined["yes_price_dollars"] = pd.to_numeric(combined["yes_price_dollars"], errors="coerce")
    combined = combined.dropna(subset=["yes_price_dollars", "created_time"])
    date_cache[ds] = combined

# ── 5. Build panel ─────────────────────────────────────────────────────────────
rows = []

for _, ev in event_meta.iterrows():
    t0           = ev["release_time_utc"]
    release_name = ev["release_name"]
    event_series = ev["event_series"]

    t_pre  = t0 - pd.Timedelta(hours=PRE_LOOKBACK_H)
    t_30m  = t0 + pd.Timedelta(minutes=30)
    t_4h   = t0 + pd.Timedelta(hours=4)
    t_24h  = t0 + pd.Timedelta(hours=24)

    # Gather cached data for this window
    date_frames = []
    cur = t_pre.date()
    while cur <= t_24h.date():
        ds = str(cur)
        if ds in date_cache:
            date_frames.append(date_cache[ds])
        cur += _td(days=1)

    if not date_frames:
        continue

    window_df = pd.concat(date_frames, ignore_index=True)
    window_df = window_df[
        (window_df["created_time"] >= t_pre) &
        (window_df["created_time"] <= t_24h)
    ].copy()

    if window_df.empty:
        continue

    for ticker, grp in window_df.groupby("ticker", sort=False):
        contract_series, month_code = ticker.split("-")[0], ticker.split("-")[1] \
            if ticker.count("-") >= 1 else (ticker, None)

        if month_code is None:
            continue

        # Expiry lookup
        key = (contract_series, month_code)
        if key in expiry_map:
            expiry = expiry_map[key]
        else:
            expiry = month_code_to_ts_approx(month_code)
            if expiry is None:
                continue

        expiry_lag_h = (expiry - t0).total_seconds() / 3600.0
        if expiry_lag_h <= EXPIRY_THRESH_H:
            continue  # settled by (or too close to) this print

        grp = grp.sort_values("created_time")

        # Pre-event prices and counts
        pre_trades     = grp[grp["created_time"] < t0]
        pre_trade_count = len(pre_trades)
        pre_price = float(pre_trades.iloc[-1]["yes_price_dollars"]) \
            if not pre_trades.empty else np.nan

        # Price at each mark (last trade at or before mark, anywhere in window)
        price_30m, stale_30m = last_price_at(grp, t_30m)
        price_4h,  stale_4h  = last_price_at(grp, t_4h)
        price_24h, stale_24h = last_price_at(grp, t_24h)

        # Post trade counts
        post_30m_count = count_in(grp, t0, t_30m)
        post_4h_count  = count_in(grp, t0, t_4h)
        post_24h_count = count_in(grp, t0, t_24h)

        usable = (pre_trade_count >= 1) and (post_24h_count >= 1)

        rows.append({
            "event_series":     event_series,
            "release_name":     release_name,
            "release_time_utc": t0,
            "ticker":           ticker,
            "contract_series":  contract_series,
            "contract_month":   month_code,
            "expiry_utc":       expiry,
            "expiry_lag_h":     round(expiry_lag_h, 1),
            "pre_price":        pre_price,
            "price_30m":        price_30m,
            "price_4h":         price_4h,
            "price_24h":        price_24h,
            "pre_trade_count":  pre_trade_count,
            "post_30m_count":   post_30m_count,
            "post_4h_count":    post_4h_count,
            "post_24h_count":   post_24h_count,
            "stale_30m_min":    stale_30m,
            "stale_4h_min":     stale_4h,
            "stale_24h_min":    stale_24h,
            "usable":           usable,
        })

panel = pd.DataFrame(rows)

# ── 6. Save ────────────────────────────────────────────────────────────────────
os.makedirs(f"{REPO}/data/clean", exist_ok=True)
panel.to_parquet(OUT_PATH, index=False)

# ── 7. Print summary only ──────────────────────────────────────────────────────
if panel.empty:
    print("No rows — no live data found for past calendar events.")
    sys.exit(0)

usable_df         = panel[panel["usable"]]
events_with_usable = usable_df["release_time_utc"].nunique()
total_usable_rows  = len(usable_df)

print(f"Events with >=1 usable market : {events_with_usable}")
print(f"Total usable event-market rows : {total_usable_rows}")
print()

# Attrition by event_series
attrition = (
    panel.groupby("event_series")
    .agg(total=("ticker", "count"), usable_n=("usable", "sum"))
    .assign(pct_usable=lambda x: (x["usable_n"] / x["total"] * 100).round(1))
    .rename(columns={"usable_n": "usable"})
    .sort_index()
)
print("Attrition by series (event_series = series of the release event):")
print(attrition.to_string())
