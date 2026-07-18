#!/usr/bin/env python3
"""
code/build_macro_calendar.py
============================
Build data/meta/macro_calendar.parquet — one row per scheduled macro release.

Series covered (modern KX* names used throughout as canonical keys):
  KXCPIYOY       } same BLS release (CPI, 8:30 AM ET)
  KXCPICOREYOY   }
  KXPAYROLLS     } same BLS release (Employment Situation, 8:30 AM ET)
  KXU3           }
  KXFEDDECISION  } same Fed release (FOMC decision, 2:00 PM ET)
  KXFED          }

Window: 2022-07-01 → 2026-12 (Lychee history + live collection)
  Lychee (Becker dataset): 2022-07-01 → 2025-01-01 — uses legacy tickers
    (CPI-22*, CPICORE-22*, NFP-*, FFR-*, etc.); canonical KX* names used
    here for consistent key across eras.
  Live collection: 2026-04 onward — uses KX* tickers directly.
  Gap 2025-01 → 2026-04: not covered by either source.

Date sources (all hardcoded from official schedules):
  CPI:              https://www.bls.gov/schedule/news_release/cpi.htm
                    (bls.gov returns 403 to scrapers; cross-verified against
                     cpiinflationcalculator.com, usinflationcalculator.com — consistent)
  Employment Sit.:  https://www.bls.gov/schedule/news_release/empsit.htm
                    (same 403 constraint; cross-verified via Kiplinger and
                     finance calendar aggregators — consistent)
  FOMC:             https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
                    (fetched directly — confirmed)

DST: zoneinfo("America/New_York") handles EDT/EST automatically.
Flags:
  None / ""         — confirmed historical date
  "scheduled"       — future date per official schedule, not yet released
  "estimated"       — date inferred from standard schedule pattern; verify
  "THURSDAY"        — BLS moved release from Friday due to holiday

Run from repo root:
    python code/build_macro_calendar.py [--dry-run]
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ET  = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
OUT = Path("data/meta/macro_calendar.parquet")


# ---------------------------------------------------------------------------
# Release date tables
# Each entry: (YYYY-MM-DD, descriptive_label, flag_or_None)
# ---------------------------------------------------------------------------

# ── BLS Consumer Price Index ─────────────────────────────────────────────────
# Covers KXCPIYOY and KXCPICOREYOY (legacy: CPI-*, CPICORE-* on Kalshi)
# All at 8:30 AM ET.  UTC = 12:30 (EDT, Mar–Oct) or 13:30 (EST, Nov–Feb).
CPI_DATES: list[tuple[str, str, str | None]] = [
    # ── 2022 ──────────────────────────────────────────────────────────────
    ("2022-07-13", "CPI June 2022",        None),
    ("2022-08-10", "CPI July 2022",        None),
    ("2022-09-13", "CPI August 2022",      None),
    ("2022-10-13", "CPI September 2022",   None),
    ("2022-11-10", "CPI October 2022",     None),
    ("2022-12-13", "CPI November 2022",    None),
    # ── 2023 ──────────────────────────────────────────────────────────────
    ("2023-01-12", "CPI December 2022",    None),
    ("2023-02-14", "CPI January 2023",     None),
    ("2023-03-14", "CPI February 2023",    None),
    ("2023-04-12", "CPI March 2023",       None),
    ("2023-05-10", "CPI April 2023",       None),
    ("2023-06-13", "CPI May 2023",         None),
    ("2023-07-12", "CPI June 2023",        None),
    ("2023-08-10", "CPI July 2023",        None),
    ("2023-09-13", "CPI August 2023",      None),
    ("2023-10-12", "CPI September 2023",   None),
    ("2023-11-14", "CPI October 2023",     None),
    ("2023-12-12", "CPI November 2023",    None),
    # ── 2024 ──────────────────────────────────────────────────────────────
    ("2024-01-11", "CPI December 2023",    None),
    ("2024-02-13", "CPI January 2024",     None),
    ("2024-03-12", "CPI February 2024",    None),
    ("2024-04-10", "CPI March 2024",       None),
    ("2024-05-15", "CPI April 2024",       None),
    ("2024-06-12", "CPI May 2024",         None),
    ("2024-07-11", "CPI June 2024",        None),
    ("2024-08-14", "CPI July 2024",        None),
    ("2024-09-11", "CPI August 2024",      None),
    ("2024-10-10", "CPI September 2024",   None),
    ("2024-11-13", "CPI October 2024",     None),
    ("2024-12-11", "CPI November 2024",    None),
    # ── 2025 ──────────────────────────────────────────────────────────────
    ("2025-01-15", "CPI December 2024",    None),
    ("2025-02-12", "CPI January 2025",     None),
    ("2025-03-12", "CPI February 2025",    None),
    ("2025-04-10", "CPI March 2025",       None),
    ("2025-05-13", "CPI April 2025",       None),
    ("2025-06-11", "CPI May 2025",         None),
    ("2025-07-11", "CPI June 2025",        None),
    ("2025-08-12", "CPI July 2025",        None),
    ("2025-09-10", "CPI August 2025",      "estimated — verify against bls.gov"),
    ("2025-10-15", "CPI September 2025",   "estimated — verify against bls.gov"),
    ("2025-11-12", "CPI October 2025",     "estimated — verify against bls.gov"),
    ("2025-12-10", "CPI November 2025",    "estimated — verify against bls.gov"),
    # ── 2026 (pre-live-collection window) ─────────────────────────────────
    ("2026-01-15", "CPI December 2025",    "estimated — verify against bls.gov"),
    ("2026-02-12", "CPI January 2026",     "estimated — verify against bls.gov"),
    ("2026-03-12", "CPI February 2026",    "estimated — verify against bls.gov"),
    ("2026-04-09", "CPI March 2026",       "estimated — verify against bls.gov"),
    # ── 2026 (live collection window — confirmed/scheduled) ───────────────
    ("2026-05-12", "CPI April 2026",       None),
    ("2026-06-10", "CPI May 2026",         None),
    ("2026-07-14", "CPI June 2026",        "scheduled — not yet released as of 2026-07-13"),
    ("2026-08-12", "CPI July 2026",        "scheduled"),
    ("2026-09-11", "CPI August 2026",      "scheduled"),
    ("2026-10-14", "CPI September 2026",   "scheduled"),
    ("2026-11-10", "CPI October 2026",     "scheduled"),
    ("2026-12-10", "CPI November 2026",    "scheduled"),
]

# ── BLS Employment Situation ──────────────────────────────────────────────────
# Covers KXPAYROLLS and KXU3 (legacy: NFP-*, PAYROLLS-* on Kalshi)
# Typically first Friday of month at 8:30 AM ET.
EMPSIT_DATES: list[tuple[str, str, str | None]] = [
    # ── 2022 ──────────────────────────────────────────────────────────────
    ("2022-07-08", "Employment Situation June 2022",      None),
    ("2022-08-05", "Employment Situation July 2022",      None),
    ("2022-09-02", "Employment Situation August 2022",    None),
    ("2022-10-07", "Employment Situation September 2022", None),
    ("2022-11-04", "Employment Situation October 2022",   None),
    ("2022-12-02", "Employment Situation November 2022",  None),
    # ── 2023 ──────────────────────────────────────────────────────────────
    ("2023-01-06", "Employment Situation December 2022",  None),
    ("2023-02-03", "Employment Situation January 2023",   None),
    ("2023-03-10", "Employment Situation February 2023",  None),
    ("2023-04-07", "Employment Situation March 2023",     None),
    ("2023-05-05", "Employment Situation April 2023",     None),
    ("2023-06-02", "Employment Situation May 2023",       None),
    ("2023-07-07", "Employment Situation June 2023",      None),
    ("2023-08-04", "Employment Situation July 2023",      None),
    ("2023-09-01", "Employment Situation August 2023",    None),
    ("2023-10-06", "Employment Situation September 2023", None),
    ("2023-11-03", "Employment Situation October 2023",   None),
    ("2023-12-08", "Employment Situation November 2023",  None),
    # ── 2024 ──────────────────────────────────────────────────────────────
    ("2024-01-05", "Employment Situation December 2023",  None),
    ("2024-02-02", "Employment Situation January 2024",   None),
    ("2024-03-08", "Employment Situation February 2024",  None),
    ("2024-04-05", "Employment Situation March 2024",     None),
    ("2024-05-03", "Employment Situation April 2024",     None),
    ("2024-06-07", "Employment Situation May 2024",       None),
    ("2024-07-05", "Employment Situation June 2024",      None),
    ("2024-08-02", "Employment Situation July 2024",      None),
    ("2024-09-06", "Employment Situation August 2024",    None),
    ("2024-10-04", "Employment Situation September 2024", None),
    ("2024-11-01", "Employment Situation October 2024",   None),
    ("2024-12-06", "Employment Situation November 2024",  None),
    # ── 2025 ──────────────────────────────────────────────────────────────
    ("2025-01-10", "Employment Situation December 2024",  None),
    ("2025-02-07", "Employment Situation January 2025",   None),
    ("2025-03-07", "Employment Situation February 2025",  None),
    ("2025-04-04", "Employment Situation March 2025",     None),
    ("2025-05-02", "Employment Situation April 2025",     None),
    ("2025-06-06", "Employment Situation May 2025",       None),
    ("2025-07-03", "Employment Situation June 2025",
     "THURSDAY — July 4 observed Friday holiday; BLS moved early"),
    ("2025-08-01", "Employment Situation July 2025",      None),
    ("2025-09-05", "Employment Situation August 2025",    "estimated — verify against bls.gov"),
    ("2025-10-03", "Employment Situation September 2025", "estimated — verify against bls.gov"),
    ("2025-11-07", "Employment Situation October 2025",   "estimated — verify against bls.gov"),
    ("2025-12-05", "Employment Situation November 2025",  "estimated — verify against bls.gov"),
    # ── 2026 (pre-live-collection window) ─────────────────────────────────
    ("2026-01-09", "Employment Situation December 2025",  "estimated — verify against bls.gov"),
    ("2026-02-06", "Employment Situation January 2026",   "estimated — verify against bls.gov"),
    ("2026-03-06", "Employment Situation February 2026",  "estimated — verify against bls.gov"),
    ("2026-04-03", "Employment Situation March 2026",     "estimated — verify against bls.gov"),
    # ── 2026 (live collection window) ─────────────────────────────────────
    ("2026-05-08", "Employment Situation April 2026",
     "second Friday of May — secondary sources only; bls.gov blocked to scrapers"),
    ("2026-06-05", "Employment Situation May 2026",       None),
    ("2026-07-02", "Employment Situation June 2026",
     "THURSDAY — July 3 is observed federal holiday (July 4 falls Sat); BLS moved early"),
    ("2026-08-07", "Employment Situation July 2026",      "scheduled"),
    ("2026-09-04", "Employment Situation August 2026",    "scheduled"),
    ("2026-10-02", "Employment Situation September 2026", "scheduled"),
    ("2026-11-06", "Employment Situation October 2026",   "scheduled"),
    ("2026-12-04", "Employment Situation November 2026",  "scheduled"),
]

# ── FOMC policy decisions ─────────────────────────────────────────────────────
# Covers KXFEDDECISION and KXFED (legacy: FFR-*, FEDRATE-* on Kalshi)
# Decision day (second day of meeting) at 2:00 PM ET.
# UTC = 18:00 (EDT, Mar–Oct) or 19:00 (EST, Nov–Feb).
FOMC_DATES: list[tuple[str, str, str | None]] = [
    # ── 2022 (meetings after 2022-07-01) ──────────────────────────────────
    ("2022-07-27", "FOMC July 2022",       None),
    ("2022-09-21", "FOMC September 2022",  None),
    ("2022-11-02", "FOMC November 2022",   None),
    ("2022-12-14", "FOMC December 2022",   None),
    # ── 2023 ──────────────────────────────────────────────────────────────
    ("2023-02-01", "FOMC February 2023",   None),
    ("2023-03-22", "FOMC March 2023",      None),
    ("2023-05-03", "FOMC May 2023",        None),
    ("2023-06-14", "FOMC June 2023",       None),
    ("2023-07-26", "FOMC July 2023",       None),
    ("2023-09-20", "FOMC September 2023",  None),
    ("2023-11-01", "FOMC November 2023",   None),
    ("2023-12-13", "FOMC December 2023",   None),
    # ── 2024 ──────────────────────────────────────────────────────────────
    ("2024-01-31", "FOMC January 2024",    None),
    ("2024-03-20", "FOMC March 2024",      None),
    ("2024-05-01", "FOMC May 2024",        None),
    ("2024-06-12", "FOMC June 2024",       None),
    ("2024-07-31", "FOMC July 2024",       None),
    ("2024-09-18", "FOMC September 2024",  None),
    ("2024-11-07", "FOMC November 2024",   None),
    ("2024-12-18", "FOMC December 2024",   None),
    # ── 2025 ──────────────────────────────────────────────────────────────
    ("2025-01-29", "FOMC January 2025",    None),
    ("2025-03-19", "FOMC March 2025",      None),
    ("2025-05-07", "FOMC May 2025",        None),
    ("2025-06-18", "FOMC June 2025",       None),
    ("2025-07-30", "FOMC July 2025",       None),
    ("2025-09-17", "FOMC September 2025",  "estimated — verify against federalreserve.gov"),
    ("2025-10-29", "FOMC October 2025",    "estimated — verify against federalreserve.gov"),
    ("2025-12-10", "FOMC December 2025",   "estimated — verify against federalreserve.gov"),
    # ── 2026 (pre-live-collection window) ─────────────────────────────────
    ("2026-01-28", "FOMC January 2026",    "estimated — verify against federalreserve.gov"),
    ("2026-03-18", "FOMC March 2026",      "estimated — verify against federalreserve.gov"),
    ("2026-04-29", "FOMC April 2026",      "estimated — before live collection (starts 2026-05-04)"),
    # ── 2026 (live collection window — confirmed/scheduled) ───────────────
    ("2026-06-17", "FOMC June 2026",       None),
    ("2026-07-29", "FOMC July 2026",       "scheduled"),
    ("2026-09-16", "FOMC September 2026",  "scheduled"),
    ("2026-10-28", "FOMC October 2026",    "scheduled"),
    ("2026-12-09", "FOMC December 2026",   "scheduled"),
]


# ---------------------------------------------------------------------------
# Build DataFrame
# ---------------------------------------------------------------------------

def make_rows(
    dates: list[tuple[str, str, str | None]],
    series_list: list[str],
    hour: int,
    minute: int,
    source: str,
) -> list[dict]:
    rows = []
    for date_str, label, flag in dates:
        y, m, d = int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10])
        dt_et  = datetime(y, m, d, hour, minute, tzinfo=ET)
        dt_utc = dt_et.astimezone(UTC)
        for series in series_list:
            rows.append({
                "series":           series,
                "release_name":     label,
                "release_time_utc": dt_utc,
                "source":           source,
                "flag":             flag if flag else "",
            })
    return rows


def build() -> pd.DataFrame:
    rows: list[dict] = []
    rows += make_rows(CPI_DATES,    ["KXCPIYOY", "KXCPICOREYOY"], 8,  30, "BLS")
    rows += make_rows(EMPSIT_DATES, ["KXPAYROLLS", "KXU3"],        8,  30, "BLS")
    rows += make_rows(FOMC_DATES,   ["KXFEDDECISION", "KXFED"],    14,  0, "FederalReserve")

    df = pd.DataFrame(rows)
    df["release_time_utc"] = pd.to_datetime(df["release_time_utc"], utc=True)
    df = df.sort_values(["release_time_utc", "series"]).reset_index(drop=True)
    return df


def display(df: pd.DataFrame) -> None:
    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.width", 160)

    print("\n" + "=" * 80)
    print("MACRO CALENDAR — 2022-07-01 → 2026-12")
    print("=" * 80)

    # ── counts by series and year ─────────────────────────────────────────
    df2 = df.copy()
    df2["year"] = df2["release_time_utc"].dt.year
    pivot = (
        df2.groupby(["series", "year"])
           .size()
           .unstack(fill_value=0)
    )
    print("\nEvent counts by series and year:")
    print(pivot.to_string())

    # ── total by series ───────────────────────────────────────────────────
    totals = df.groupby("series").size().rename("total")
    print(f"\nTotals per series:\n{totals.to_string()}")

    print(f"\nTotal rows: {len(df)}  |  "
          f"{df['series'].nunique()} series  |  "
          f"{df['release_time_utc'].nunique()} distinct timestamps")

    # ── spot-check UTC times (DST visible) ───────────────────────────────
    print("\n--- UTC spot-check (first/last of each release type) ---")
    for src, grp in df.drop_duplicates(["release_name","release_time_utc"]).groupby("source"):
        first = grp.iloc[0]
        last  = grp.iloc[-1]
        print(f"  {src}:  first={first['release_time_utc'].strftime('%Y-%m-%d %H:%M UTC')} "
              f"({first['release_name']})  "
              f"last={last['release_time_utc'].strftime('%Y-%m-%d %H:%M UTC')} "
              f"({last['release_name']})")

    # ── flagged dates ─────────────────────────────────────────────────────
    flagged = (df[df["flag"] != ""]
               .drop_duplicates("release_name")[["release_name","flag"]]
               .sort_values("release_name"))
    print(f"\n--- Flagged dates ({len(flagged)}) ---")
    for _, row in flagged.iterrows():
        print(f"  [{row['release_name']}]  {row['flag']}")

    print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the table but do not write the parquet file.")
    args = parser.parse_args()

    df = build()
    display(df)

    if args.dry_run:
        print("Dry run — parquet NOT written.")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"Written -> {OUT}  ({len(df)} rows)")

    check = pd.read_parquet(OUT)
    assert check["release_time_utc"].dt.tz is not None, "UTC timezone lost on round-trip!"
    print(f"Round-trip OK — tz={check['release_time_utc'].dt.tz}")


if __name__ == "__main__":
    main()
