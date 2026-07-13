"""
ufc_crosswalk.py — Build Kalshi ↔ Polymarket UFC fight crosswalk

Stages:
  1. Load + parse Kalshi KXUFC markets (453 rows → ~226 fight entities)
  2. Load + parse Polymarket UFC markets (2097 rows)
  3. Match on event date (±1 day) + normalized fighter surname overlap
  4. Output data/meta/ufc_crosswalk.parquet
  5. Print match summary + all fuzzy/unmatched rows
  6. Validation plots: top-5 volume fights, last 72h price overlay
"""

import glob, io, json, re, sys, unicodedata, warnings
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pyarrow.compute as pc
import pyarrow as pa
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message="Converting to PeriodArray")

# ─── paths ───────────────────────────────────────────────────────────────────
LYCHEE_EXTRACT  = Path(r"C:\Kalshi_data\lychee\extracted\data")
REPO            = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
PM_TRADES       = REPO / "data" / "interim" / "polymarket_ufc_trades.parquet"
OUT_CROSSWALK   = REPO / "data" / "meta" / "ufc_crosswalk.parquet"
OUT_VAL_DIR     = Path(r"C:\Kalshi_data\lychee\qa\crosswalk_validation")
K_TRADES_DIR    = LYCHEE_EXTRACT / "kalshi" / "trades"
K_MARKETS_DIR   = LYCHEE_EXTRACT / "kalshi" / "markets"
PM_MARKETS_DIR  = LYCHEE_EXTRACT / "polymarket" / "markets"

OUT_CROSSWALK.parent.mkdir(parents=True, exist_ok=True)
OUT_VAL_DIR.mkdir(parents=True, exist_ok=True)

# ─── helpers ─────────────────────────────────────────────────────────────────
MONTH3 = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
           "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

def norm_name(s: str) -> str:
    """Lowercase, strip diacritics, keep only a-z and spaces."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z\s]", "", s.lower())
    return s.strip()

def surnames(full: str) -> set[str]:
    """Return set of non-trivial word tokens from a name (for fuzzy matching)."""
    parts = norm_name(full).split()
    # drop very short tokens and common prefixes
    skip = {"de","da","el","al","van","von","le","la","los","del","jr","sr","ii","iii"}
    return {p for p in parts if len(p) >= 3 and p not in skip}

def parse_kalshi_ticker(ticker: str):
    """
    KXUFCFIGHT-25NOV15BRAMOR-MOR
    → event_date=2025-11-15, fight_code='BRAMOR', fighter_code='MOR'
    """
    m = re.match(r"KXUFCFIGHT-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)-([A-Z]+)$", ticker)
    if not m:
        return None
    yy, mon, dd, fight_code, fighter_code = m.groups()
    year = 2000 + int(yy)
    month = MONTH3.get(mon)
    if not month:
        return None
    try:
        date = pd.Timestamp(year=year, month=month, day=int(dd)).date()
    except ValueError:
        return None
    return date, fight_code, fighter_code

def extract_pm_date_fighters(row) -> tuple[pd.Timestamp | None, list[str]]:
    """Extract (fight_date, [fighter_names]) from a Polymarket market row."""
    slug = str(row["slug"])
    outcomes_raw = row.get("outcomes", "[]")
    outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else (outcomes_raw or [])

    # Named outcomes → fighter names (not Yes/No)
    named_outcomes = [o for o in outcomes if o.lower() not in ("yes", "no")]

    # 1. Modern format: ufc-f1-vs-f2-YYYY-MM-DD
    m_date = re.search(r"(\d{4}-\d{2}-\d{2})$", slug)
    if m_date:
        try:
            d = pd.Timestamp(m_date.group(1)).date()
        except Exception:
            d = None
        if named_outcomes:
            fighters = named_outcomes
        else:
            # Strip date suffix and "ufc-" prefix, split on "-vs-"
            body = slug[: m_date.start()].rstrip("-")
            body = re.sub(r"^ufc-", "", body)
            parts = re.split(r"-vs-", body, maxsplit=1)
            fighters = [p.replace("-", " ").strip() for p in parts]
        return d, fighters

    # 2. Will-X-win format
    if slug.startswith("will-"):
        # Extract fighter name from question if possible
        q = str(row.get("question", ""))
        m_q = re.match(r"Will\s+(.+?)\s+(?:win|beat|defeat)", q, re.IGNORECASE)
        if m_q:
            fighter = m_q.group(1).strip()
        else:
            # Fall back to slug: will-{fighter}-win-...
            slug_body = re.sub(r"^will-", "", slug)
            # Take everything before "-win-" or "-beat-"
            slug_body = re.split(r"-win-|-beat-|-defeat-", slug_body)[0]
            fighter = slug_body.replace("-", " ").strip()
        fighters = [fighter]
        d = row.get("end_date")
        if d is not None:
            d = pd.Timestamp(d).date()
        return d, fighters

    # 3. Who-will-win format: extract from named outcomes or slug "vs" clause
    if named_outcomes:
        fighters = named_outcomes
        d = row.get("end_date")
        if d is not None:
            d = pd.Timestamp(d).date()
        return d, fighters

    # try to extract from slug: "...X-vs-Y..."
    m_vs = re.search(r"([a-z](?:[a-z-]*))-vs-([a-z](?:[a-z-]*))", slug)
    if m_vs:
        fighters = [m_vs.group(1).replace("-", " "), m_vs.group(2).replace("-", " ")]
    else:
        fighters = []
    d = row.get("end_date")
    if d is not None:
        d = pd.Timestamp(d).date()
    return d, fighters

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Parse Kalshi KXUFC markets
# ─────────────────────────────────────────────────────────────────────────────
print("[stage1] loading Kalshi KXUFC markets...")
k_files = sorted(K_MARKETS_DIR.glob("*.parquet"))
k_rows = []
for f in k_files:
    df = pd.read_parquet(f, columns=["ticker","title","volume","close_time","result"])
    ufc = df[df["ticker"].str.startswith("KXUFC", na=False)]
    if len(ufc):
        k_rows.append(ufc)
k_all = pd.concat(k_rows, ignore_index=True)
print(f"  {len(k_all)} KXUFC market rows")

# Parse ticker → fight entities
# Each fight has 2 rows (one per fighter). Group by (date, fight_code).
fight_rows = {}  # (date, fight_code) → list of {ticker, fighter_code, full_name, volume}
for _, row in k_all.iterrows():
    parsed = parse_kalshi_ticker(row["ticker"])
    if not parsed:
        continue
    date, fight_code, fighter_code = parsed

    # Extract full name from title
    m = re.match(r"Will (.+?) win the .+ vs .+ professional MMA", row["title"])
    full_name = m.group(1).strip() if m else ""

    key = (date, fight_code)
    if key not in fight_rows:
        fight_rows[key] = []
    fight_rows[key].append({
        "ticker":       row["ticker"],
        "fighter_code": fighter_code,
        "full_name":    full_name,
        "volume":       row.get("volume", 0) or 0,
        "result":       row.get("result", ""),
    })

# Build fight-level entities
kalshi_fights = []
for (date, fight_code), members in fight_rows.items():
    if len(members) < 2:
        # Might be 1 row in a multi-file scan if duplicate pages; take what we have
        f1, f2 = members[0], {"ticker":"","fighter_code":"","full_name":"","volume":0}
    else:
        f1, f2 = members[0], members[1]
    total_vol = sum(m["volume"] for m in members)
    tickers   = [m["ticker"] for m in members]
    names     = [m["full_name"] for m in members if m["full_name"]]
    kalshi_fights.append({
        "fight_id":       f"{date.strftime('%Y%m%d')}_{fight_code}",
        "event_date":     pd.Timestamp(date),
        "fight_code":     fight_code,
        "fighters_kalshi": names,
        "tickers":        tickers,
        "kalshi_volume":  total_vol,
        "members":        members,  # keep for fighter code lookup
    })

kf = pd.DataFrame(kalshi_fights)
kf = kf.sort_values("event_date").reset_index(drop=True)
print(f"  {len(kf)} unique Kalshi fight entities")
print(f"  date range: {kf['event_date'].min().date()} -> {kf['event_date'].max().date()}")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Parse Polymarket UFC markets
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage2] loading Polymarket UFC markets...")
pm_files = sorted(PM_MARKETS_DIR.glob("*.parquet"))
pm_dfs = [pd.read_parquet(f) for f in pm_files]
pm_all = pd.concat(pm_dfs, ignore_index=True)

pm_ufc = pm_all[pm_all["slug"].str.contains("ufc|mma", case=False, na=False)].copy()
pm_ufc["end_date"] = pd.to_datetime(pm_ufc["end_date"], utc=True, errors="coerce")
print(f"  {len(pm_ufc)} UFC/MMA markets")

# Parse each market
pm_parsed = []
for _, row in pm_ufc.iterrows():
    try:
        fight_date, fighters = extract_pm_date_fighters(row)
    except Exception:
        fight_date, fighters = None, []

    outcomes_raw = row.get("outcomes", "[]")
    outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else []
    clob_raw = row.get("clob_token_ids", "[]")
    clob = json.loads(clob_raw) if isinstance(clob_raw, str) else []

    pm_parsed.append({
        "pm_id":         row["id"],
        "slug":          row["slug"],
        "question":      row.get("question", ""),
        "fight_date":    pd.Timestamp(fight_date) if fight_date else pd.NaT,
        "end_date":      row["end_date"],
        "fighters_pm":   fighters,
        "outcomes":      outcomes,
        "clob_token_ids": clob,
        "volume":        float(row.get("volume", 0) or 0),
    })

pmf = pd.DataFrame(pm_parsed)
pmf = pmf.dropna(subset=["fight_date"]).reset_index(drop=True)
print(f"  {len(pmf)} with parseable fight date")

# Pre-compute normalized surname sets for matching
pmf["surnames_pm"] = pmf["fighters_pm"].apply(
    lambda fs: {s for f in fs for s in surnames(f)}
)

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — Match Kalshi ↔ Polymarket
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage3] matching fights...")

def match_fight(krow):
    """Find best Polymarket match for a Kalshi fight."""
    k_date   = krow["event_date"].date()
    k_names  = krow["fighters_kalshi"]
    k_snames = {s for n in k_names for s in surnames(n)}

    # Date filter: ±1 day
    lo = pd.Timestamp(k_date) - pd.Timedelta(days=1)
    hi = pd.Timestamp(k_date) + pd.Timedelta(days=1)
    candidates = pmf[(pmf["fight_date"] >= lo) & (pmf["fight_date"] <= hi)].copy()
    if candidates.empty:
        return None, "unmatched", 0

    # Score by surname overlap
    def overlap(pm_snames):
        return len(k_snames & pm_snames)

    candidates = candidates.copy()
    candidates["overlap"] = candidates["surnames_pm"].apply(overlap)
    best_overlap = candidates["overlap"].max()

    if best_overlap == 0:
        return None, "unmatched", 0

    best_candidates = candidates[candidates["overlap"] == best_overlap]

    # Among ties, prefer highest volume
    best = best_candidates.sort_values("volume", ascending=False).iloc[0]

    # Determine confidence
    n_k = len(k_snames)
    n_pm = len(best["surnames_pm"]) if best["surnames_pm"] else 1
    if best_overlap >= 2 or (n_k >= 2 and best_overlap / max(n_k, 1) >= 0.5):
        confidence = "exact"
    else:
        confidence = "fuzzy"

    return best, confidence, best_overlap

crosswalk_rows = []
for _, krow in kf.iterrows():
    best_pm, confidence, overlap_n = match_fight(krow)

    row = {
        "fight_id":           krow["fight_id"],
        "event_date":         krow["event_date"],
        "fighters_kalshi":    krow["fighters_kalshi"],
        "tickers":            krow["tickers"],
        "kalshi_volume":      krow["kalshi_volume"],
        "match_confidence":   confidence,
        "overlap_count":      overlap_n,
        # Polymarket fields (None if unmatched)
        "pm_id":              None,
        "pm_slug":            None,
        "pm_fight_date":      pd.NaT,
        "fighters_pm":        None,
        "outcomes":           None,
        "clob_token_ids":     None,
        "pm_volume":          0.0,
    }
    if best_pm is not None:
        row.update({
            "pm_id":          best_pm["pm_id"],
            "pm_slug":        best_pm["slug"],
            "pm_fight_date":  best_pm["fight_date"],
            "fighters_pm":    best_pm["fighters_pm"],
            "outcomes":       best_pm["outcomes"],
            "clob_token_ids": best_pm["clob_token_ids"],
            "pm_volume":      best_pm["volume"],
        })
    crosswalk_rows.append(row)

cw = pd.DataFrame(crosswalk_rows)

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — Save crosswalk parquet
# ─────────────────────────────────────────────────────────────────────────────
# Serialize list columns to JSON strings for parquet storage
cw_save = cw.copy()
for col in ["fighters_kalshi","tickers","fighters_pm","outcomes","clob_token_ids"]:
    cw_save[col] = cw_save[col].apply(lambda x: json.dumps(x) if x is not None else None)

cw_save.to_parquet(OUT_CROSSWALK, index=False)
print(f"\n[stage4] saved {OUT_CROSSWALK}  ({len(cw_save)} rows)")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5 — Match summary + fuzzy/unmatched for manual review
# ─────────────────────────────────────────────────────────────────────────────
n_total   = len(cw)
n_exact   = (cw["match_confidence"] == "exact").sum()
n_fuzzy   = (cw["match_confidence"] == "fuzzy").sum()
n_unmatched = (cw["match_confidence"] == "unmatched").sum()

print("\n" + "="*65)
print("UFC VENUE CROSSWALK — MATCH SUMMARY")
print("="*65)
print(f"Kalshi KXUFC fights:   {n_total}")
print(f"  exact matches:       {n_exact}  ({n_exact/n_total*100:.1f}%)")
print(f"  fuzzy matches:       {n_fuzzy}  ({n_fuzzy/n_total*100:.1f}%)")
print(f"  unmatched:           {n_unmatched}  ({n_unmatched/n_total*100:.1f}%)")

print("\n── FUZZY MATCHES (needs manual review) ──")
fuz = cw[cw["match_confidence"] == "fuzzy"].copy()
if fuz.empty:
    print("  (none)")
else:
    for _, r in fuz.iterrows():
        k_names = ", ".join(r["fighters_kalshi"])
        pm_names = ", ".join(r["fighters_pm"]) if r["fighters_pm"] else "?"
        print(f"  {r['event_date'].date()}  K=[{k_names}]  PM=[{pm_names}]  slug={r['pm_slug']}")

print("\n── UNMATCHED KALSHI FIGHTS ──")
unm = cw[cw["match_confidence"] == "unmatched"].copy()
if unm.empty:
    print("  (none)")
else:
    for _, r in unm.iterrows():
        k_names = ", ".join(r["fighters_kalshi"])
        print(f"  {r['event_date'].date()}  [{k_names}]  tickers={r['tickers']}")

print("\n── TOP 20 EXACT MATCHES (by Kalshi volume) ──")
top_exact = cw[cw["match_confidence"] == "exact"].nlargest(20, "kalshi_volume")
for _, r in top_exact.iterrows():
    k = ", ".join(r["fighters_kalshi"])
    pm = r["pm_slug"] or ""
    print(f"  {r['event_date'].date()}  [{k}]  vol={r['kalshi_volume']:,}  slug={pm}")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6 — Validation plots: top 5 fights by Polymarket trade count
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage6] loading Polymarket UFC trades for validation...")
pm_trades = pd.read_parquet(PM_TRADES)
pm_trades["ts_utc"] = pd.to_datetime(pm_trades["ts_utc"], utc=True)

# PM trade volume per market_id (row count as proxy)
pm_vol_by_market = pm_trades.groupby("market_id").size().rename("pm_trade_count")

# Matched fights with pm_id
matched = cw[cw["pm_id"].notna()].copy()
matched["pm_trade_count"] = matched["pm_id"].map(pm_vol_by_market).fillna(0)

# Top 5 by PM trade count
top5 = matched.nlargest(5, "pm_trade_count")
print(f"  top 5 fights by PM trade count:")
for _, r in top5.iterrows():
    print(f"    {r['event_date'].date()}  {r['fighters_kalshi']}  pm_trades={int(r['pm_trade_count']):,}")

# ── Load Kalshi KXUFC trades for the top 5 fights ──────────────────────────
top5_tickers = set()
top5_pm_ids  = set()
for _, r in top5.iterrows():
    for t in r["tickers"]:
        top5_tickers.add(t)
    top5_pm_ids.add(r["pm_id"])

print(f"\n  scanning Kalshi trades for {len(top5_tickers)} tickers across {len(list(K_TRADES_DIR.glob('*.parquet')))} files...")
k_trade_files = sorted(K_TRADES_DIR.glob("*.parquet"))
k_chunks = []
token_arr_filter = pa.array(list(top5_tickers))
for f in k_trade_files:
    try:
        tbl = pq.read_table(f, columns=["ticker","yes_price","count","created_time"])
        mask = pc.is_in(tbl.column("ticker"), value_set=token_arr_filter)
        hit = tbl.filter(mask)
        if hit.num_rows > 0:
            k_chunks.append(hit.to_pandas())
    except Exception:
        continue

k_trades = pd.concat(k_chunks, ignore_index=True) if k_chunks else pd.DataFrame()
k_trades["created_time"] = pd.to_datetime(k_trades["created_time"], utc=True)
print(f"  {len(k_trades):,} Kalshi UFC trade rows for top-5 fights")

# ── Plot price overlay for each top-5 fight ────────────────────────────────
print("\n  generating validation plots...")

for i, (_, fight) in enumerate(top5.iterrows(), 1):
    pm_id     = fight["pm_id"]
    tickers   = fight["tickers"]
    k_names   = fight["fighters_kalshi"]
    pm_names  = fight["fighters_pm"] if fight["fighters_pm"] else k_names
    outcomes  = fight["outcomes"] if fight["outcomes"] else ["YES", "NO"]
    fight_dt  = pd.Timestamp(fight["event_date"]).tz_localize("UTC")
    slug      = fight["pm_slug"] or ""

    # Window: fight_dt - 72h  to  fight_dt + 4h
    t_end   = fight_dt + pd.Timedelta(hours=4)
    t_start = fight_dt - pd.Timedelta(hours=72)

    # Polymarket traces — one line per fighter (outcome)
    pm_fight = pm_trades[pm_trades["market_id"] == pm_id].copy()
    pm_fight = pm_fight[(pm_fight["ts_utc"] >= t_start) & (pm_fight["ts_utc"] <= t_end)]
    pm_fight = pm_fight.sort_values("ts_utc")

    # Kalshi traces — one line per ticker
    k_fight = k_trades[k_trades["ticker"].isin(tickers)].copy()
    k_fight = k_fight[(k_fight["created_time"] >= t_start) & (k_fight["created_time"] <= t_end)]
    k_fight = k_fight.sort_values("created_time")

    # Determine which Kalshi ticker corresponds to which PM outcome (YES = outcomes[0])
    # Kalshi: each ticker ends with a fighter code. Fighter code corresponds to one name.
    # PM: outcomes[0] = YES token (price_yes from PM = P(outcomes[0] wins))
    # We need one consistent fighter to compare.
    #
    # Strategy: pick the fighter who is outcomes[0] on PM (if matched), use their Kalshi ticker.
    pm_yes_name = norm_name(pm_names[0]) if pm_names else ""

    # Find the Kalshi ticker for the fighter closest to pm_yes_name
    best_kticker = None
    best_score   = 0
    for t in tickers:
        parsed = parse_kalshi_ticker(t)
        if not parsed:
            continue
        _, _, fcode = parsed
        # find the member with this fighter_code
        fight_members = kf[kf["fight_id"] == fight["fight_id"]].iloc[0]["members"] if len(kf[kf["fight_id"] == fight["fight_id"]]) else []
        for m in fight_members:
            if m["fighter_code"] == fcode:
                fn_norm = norm_name(m["full_name"])
                # score = number of common tokens
                score = len(set(fn_norm.split()) & set(pm_yes_name.split()))
                if score > best_score:
                    best_score = score
                    best_kticker = t
                break

    if best_kticker is None and tickers:
        best_kticker = tickers[0]

    # PM price: price_yes already = P(YES outcome = outcomes[0] wins)
    # Kalshi price for best_kticker: yes_price / 100
    k_yes = k_fight[k_fight["ticker"] == best_kticker].copy()
    k_yes["price"] = k_yes["yes_price"] / 100.0

    # OHLC-style binning to 15-min intervals for cleaner visualization
    def resample_prices(df, time_col, price_col, rule="15min"):
        if df.empty:
            return pd.DataFrame(columns=[time_col, price_col])
        df = df.set_index(time_col)[price_col].resample(rule).last().dropna()
        return df.reset_index()

    k_resampled  = resample_prices(k_yes, "created_time", "price")
    pm_resampled = resample_prices(pm_fight, "ts_utc", "price_yes")

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 5))

    fighter_yes = pm_names[0] if pm_names else "Fighter A"
    fighter_no  = pm_names[1] if len(pm_names) > 1 else "Fighter B"

    # PM trace
    if not pm_resampled.empty:
        ax.step(pm_resampled["ts_utc"], pm_resampled["price_yes"],
                where="post", color="#2196F3", linewidth=1.5,
                label=f"Polymarket  P({fighter_yes} wins)", alpha=0.9)

    # Kalshi trace
    if not k_resampled.empty:
        ax.step(k_resampled["created_time"], k_resampled["price"],
                where="post", color="#F44336", linewidth=1.5, linestyle="--",
                label=f"Kalshi  P({fighter_yes} wins)", alpha=0.9)

    ax.axhline(0.5, color="grey", linewidth=0.7, linestyle=":")
    ax.axvline(fight_dt, color="black", linewidth=1.2, linestyle="-", alpha=0.5,
               label="Fight time")

    ax.set_ylim(-0.02, 1.02)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
    fig.autofmt_xdate(rotation=0, ha="center")

    pm_rows = len(pm_fight)
    k_rows  = len(k_yes)
    ax.set_title(
        f"#{i} {fight['event_date'].date()}  {' vs '.join(k_names)}\n"
        f"PM: {pm_rows:,} trades  |  Kalshi: {k_rows:,} trades  |  slug: {slug}",
        fontsize=10
    )
    ax.set_xlabel("UTC time (last 72h before fight)")
    ax.set_ylabel(f"P({fighter_yes} wins)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    fight_code_str = fight["fight_id"].split("_")[-1] if "_" in fight["fight_id"] else fight["fight_id"]
    safe_name = re.sub(r"[^\w\-]", "_", f"{fight['event_date'].date()}_{fight_code_str}")
    out_path = OUT_VAL_DIR / f"val_{i:02d}_{safe_name}.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    # Convergence check
    if not pm_resampled.empty and not k_resampled.empty:
        # Interpolate PM onto Kalshi timestamps and compute mean abs diff
        pm_interp = np.interp(
            k_resampled["created_time"].astype("int64"),
            pm_resampled["ts_utc"].astype("int64"),
            pm_resampled["price_yes"]
        )
        mad = np.abs(pm_interp - k_resampled["price"].values).mean()
        flag = " *** DIVERGES" if mad > 0.10 else ""
        print(f"  [{i}] {fight['event_date'].date()}  MAD={mad:.3f}{flag}  → {out_path.name}")
    else:
        print(f"  [{i}] {fight['event_date'].date()}  insufficient data for convergence check  → {out_path.name}")

print(f"\nDone. Plots saved to {OUT_VAL_DIR}")
print(f"Crosswalk: {OUT_CROSSWALK}")
