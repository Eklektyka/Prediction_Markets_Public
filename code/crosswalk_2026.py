"""
crosswalk_2026.py — Extend UFC crosswalk to 2026_collector era.

Uses FROZEN matching logic from ufc_crosswalk.py:
  date ±1 day + surname overlap, named_outcome side assignment,
  bare-slug secondary pass (already baked into PM gap-fill discovery).

Inputs:
  data/interim/kxufcfight_2026_markets.parquet  (Kalshi API cache, 250 rows)
  data/interim/pm_gapfill_trades.parquet        (284,968 trades, 1,565 markets)
  data/raw/pm_gapfill/markets_discovered.json   (PM token metadata)
  data/meta/ufc_crosswalk.parquet               (existing 2025_lychee crosswalk)

Outputs:
  data/meta/ufc_crosswalk.parquet               (appended, era column added)
  qa/crosswalk_2026.md                          (match summary + review list)
  qa/crosswalk_validation/val2026_*.png         (MAD plots, top-5 fights, 24h)

STOP after printing review list. No panel build.

Expected runtime: ~60s (API market load + file scan for top-5 MAD).
"""

import glob, json, re, sys, unicodedata, warnings
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore", category=FutureWarning)

# ─── paths ────────────────────────────────────────────────────────────────────
REPO         = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
K26_MARKETS  = REPO / "data" / "interim" / "kxufcfight_2026_markets.parquet"
PM_TRADES    = REPO / "data" / "interim" / "pm_gapfill_trades.parquet"
PM_MKTS_JSON = REPO / "data" / "raw" / "pm_gapfill" / "markets_discovered.json"
OUT_CW       = REPO / "data" / "meta" / "ufc_crosswalk.parquet"
VAL_DIR      = REPO / "qa" / "crosswalk_validation"
QA_MD        = REPO / "qa" / "crosswalk_2026.md"
LIVE_DIR     = REPO / "data" / "raw" / "live"

VAL_DIR.mkdir(parents=True, exist_ok=True)

# ─── helpers (frozen from ufc_crosswalk.py) ───────────────────────────────────
MONTH3 = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
           "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\s]", "", s.lower()).strip()

def surnames(full: str) -> set[str]:
    parts = norm_name(full).split()
    skip = {"de","da","el","al","van","von","le","la","los","del","jr","sr","ii","iii"}
    return {p for p in parts if len(p) >= 3 and p not in skip}

def parse_kalshi_ticker(ticker: str):
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

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Parse Kalshi 2026 markets
# ─────────────────────────────────────────────────────────────────────────────
print("[stage1] loading Kalshi 2026 KXUFCFIGHT markets (API cache)...")
k26 = pd.read_parquet(K26_MARKETS)
print(f"  {len(k26)} market rows, {k26['ticker'].nunique()} unique tickers")

# Parse tickers → fight entities
fight_rows = {}  # (date, fight_code) → list of members
for _, row in k26.iterrows():
    parsed = parse_kalshi_ticker(row["ticker"])
    if not parsed:
        continue
    date, fight_code, fighter_code = parsed

    # Extract full name from title: "Will {NAME} win the X vs Y professional MMA..."
    m = re.match(r"Will (.+?) win the .+ vs .+ professional MMA", str(row["title"]))
    full_name = m.group(1).strip() if m else ""

    key = (date, fight_code)
    if key not in fight_rows:
        fight_rows[key] = []
    fight_rows[key].append({
        "ticker":       row["ticker"],
        "fighter_code": fighter_code,
        "full_name":    full_name,
        "volume":       float(row.get("volume", 0) or 0),
        "close_time":   row.get("close_time", ""),
    })

kalshi_fights = []
for (date, fight_code), members in fight_rows.items():
    if len(members) < 2:
        f2 = {"ticker":"","fighter_code":"","full_name":"","volume":0}
        members = members + [f2]
    total_vol  = sum(m["volume"] for m in members)
    tickers    = [m["ticker"] for m in members if m["ticker"]]
    names      = [m["full_name"] for m in members if m["full_name"]]
    close_time = members[0].get("close_time", "")
    kalshi_fights.append({
        "fight_id":        f"{date.strftime('%Y%m%d')}_{fight_code}",
        "event_date":      pd.Timestamp(date),
        "fight_code":      fight_code,
        "fighters_kalshi": names,
        "tickers":         tickers,
        "kalshi_volume":   total_vol,
        "members":         members,
        "close_time_raw":  close_time,
    })

kf = pd.DataFrame(kalshi_fights).sort_values("event_date").reset_index(drop=True)
print(f"  {len(kf)} unique fight entities")
print(f"  date range: {kf['event_date'].min().date()} -> {kf['event_date'].max().date()}")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Parse PM 2026 fight-winner markets from gap-fill trades
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage2] loading PM gap-fill markets...")
pmg = pd.read_parquet(PM_TRADES, columns=[
    "condition_id","market_slug","question","outcome","token_id","timestamp","price_yes"
])

# Build per-market metadata
NON_FIGHTER = {"yes","no","over","under","draw",""}
pm_meta = (
    pmg.groupby("condition_id")
    .agg(
        market_slug=("market_slug","first"),
        question=("question","first"),
        outcomes=("outcome", lambda x: sorted({o for o in x.unique() if o.lower() not in NON_FIGHTER})),
        n_trades=("price_yes","count"),
        min_ts=("timestamp","min"),
        max_ts=("timestamp","max"),
    )
    .reset_index()
)
print(f"  {len(pm_meta)} unique PM markets total")

# Fight-winner: ≥2 named outcomes (all non-standard)
fw_mask = pm_meta["outcomes"].apply(lambda x: len(x) >= 2)
pmf_all = pm_meta[fw_mask].copy().reset_index(drop=True)
print(f"  {len(pmf_all)} fight-winner markets (>=2 named outcomes)")

# Extract fight_date from market_slug trailing YYYY-MM-DD
def slug_date(slug: str):
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", str(slug))
    if m:
        try:
            return pd.Timestamp(m.group(1)).date()
        except Exception:
            pass
    return None

pmf_all["fight_date_raw"] = pmf_all["market_slug"].apply(slug_date)
pmf_all = pmf_all.dropna(subset=["fight_date_raw"]).reset_index(drop=True)
pmf_all["fight_date"] = pd.to_datetime(pmf_all["fight_date_raw"].apply(lambda d: pd.Timestamp(d)))
print(f"  {len(pmf_all)} with parseable fight date")
print(f"  PM date range: {pmf_all['fight_date'].min().date()} -> {pmf_all['fight_date'].max().date()}")

# Token metadata from discovered.json (for clob_token_ids)
pm_token_map = {}  # condition_id → [token_ids]
if PM_MKTS_JSON.exists():
    disc = json.loads(PM_MKTS_JSON.read_text())
    for m in disc:
        cid = m.get("condition_id","")
        if cid:
            pm_token_map[cid] = m.get("token_ids", [])

# Outcome → token_id mapping per market (from trades)
tok_df = pmg[["condition_id","outcome","token_id"]].drop_duplicates(["condition_id","outcome"])
tok_lookup = {}  # condition_id → {outcome: token_id}
for cid, grp in tok_df.groupby("condition_id"):
    tok_lookup[cid] = dict(zip(grp["outcome"], grp["token_id"]))

# Pre-compute surname sets
pmf_all["surnames_pm"] = pmf_all["outcomes"].apply(
    lambda fs: {s for f in fs for s in surnames(f)}
)

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — Match (frozen logic)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage3] matching 2026 fights...")

def match_fight(krow):
    k_date  = krow["event_date"].date()
    k_names = krow["fighters_kalshi"]
    k_snames = {s for n in k_names for s in surnames(n)}

    lo = pd.Timestamp(k_date) - pd.Timedelta(days=1)
    hi = pd.Timestamp(k_date) + pd.Timedelta(days=1)
    cands = pmf_all[
        (pmf_all["fight_date"] >= lo) & (pmf_all["fight_date"] <= hi)
    ].copy()
    if cands.empty:
        return None, "unmatched", 0

    def overlap(pm_snames):
        return len(k_snames & pm_snames)

    cands["overlap"] = cands["surnames_pm"].apply(overlap)
    best_overlap = cands["overlap"].max()
    if best_overlap == 0:
        return None, "unmatched", 0

    best_cands = cands[cands["overlap"] == best_overlap]
    best = best_cands.sort_values("n_trades", ascending=False).iloc[0]

    n_k = len(k_snames)
    if best_overlap >= 2 or (n_k >= 2 and best_overlap / max(n_k, 1) >= 0.5):
        confidence = "exact"
    else:
        confidence = "fuzzy"

    return best, confidence, best_overlap

crosswalk_rows = []
for _, krow in kf.iterrows():
    best_pm, confidence, overlap_n = match_fight(krow)
    cid = best_pm["condition_id"] if best_pm is not None else None

    row = {
        "fight_id":          krow["fight_id"],
        "event_date":        krow["event_date"],
        "era":               "2026_collector",
        "fighters_kalshi":   krow["fighters_kalshi"],
        "tickers":           krow["tickers"],
        "kalshi_volume":     krow["kalshi_volume"],
        "match_confidence":  confidence,
        "overlap_count":     overlap_n,
        "pm_id":             cid,
        "pm_slug":           best_pm["market_slug"] if best_pm is not None else None,
        "pm_fight_date":     best_pm["fight_date"]  if best_pm is not None else pd.NaT,
        "fighters_pm":       best_pm["outcomes"]     if best_pm is not None else None,
        "outcomes":          best_pm["outcomes"]     if best_pm is not None else None,
        "clob_token_ids":    pm_token_map.get(cid, []) if cid else None,
        "pm_volume":         float(best_pm["n_trades"]) if best_pm is not None else 0.0,
    }
    crosswalk_rows.append(row)

cw26 = pd.DataFrame(crosswalk_rows)
print(f"  built {len(cw26)} crosswalk rows")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — Side assignment check (named_outcome vs fallback)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage4] side assignment check...")
n_named = 0
n_fallback = 0
fallback_rows = []

for _, row in cw26[cw26["match_confidence"] != "unmatched"].iterrows():
    k_names   = row["fighters_kalshi"] or []
    pm_names  = row["fighters_pm"]     or []
    assigned  = []
    for kn in k_names:
        k_sn = surnames(kn)
        match_found = any(k_sn & surnames(pn) for pn in pm_names)
        assigned.append(match_found)
    if all(assigned):
        n_named += 1
    else:
        n_fallback += 1
        fallback_rows.append({
            "fight_id":  row["fight_id"],
            "k_names":   k_names,
            "pm_names":  pm_names,
        })

print(f"  named_outcome: {n_named}")
print(f"  fallback:      {n_fallback}")
if fallback_rows:
    print("  *** FLAG: fallback side assignment needed for:")
    for r in fallback_rows:
        print(f"    {r['fight_id']}  K={r['k_names']}  PM={r['pm_names']}")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5 — Append to crosswalk with era column
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage5] appending to crosswalk...")
cw25 = pd.read_parquet(OUT_CW)
# Serialize list cols
def to_json(x):
    return json.dumps(x) if x is not None else None

if "era" not in cw25.columns:
    cw25["era"] = "2025_lychee"
else:
    # Drop any previously appended 2026 rows (idempotent re-runs)
    cw25 = cw25[cw25["era"] == "2025_lychee"].copy()

# Normalize 2026 list cols for parquet
cw26_save = cw26.copy()
for col in ["fighters_kalshi","tickers","fighters_pm","outcomes","clob_token_ids"]:
    cw26_save[col] = cw26_save[col].apply(to_json)

# Align columns: add missing era to cw25 save cols
cw25_save = cw25.copy()

# Column order: use existing + any new from 2026
all_cols = list(cw25_save.columns)
for c in cw26_save.columns:
    if c not in all_cols:
        all_cols.append(c)
        cw25_save[c] = None

cw26_save = cw26_save.reindex(columns=all_cols)

combined = pd.concat([cw25_save, cw26_save], ignore_index=True)
combined.to_parquet(OUT_CW, index=False)
print(f"  saved {OUT_CW}  ({len(combined)} rows total: {len(cw25)} lychee + {len(cw26_save)} collector)")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6 — Print match summary + review list
# ─────────────────────────────────────────────────────────────────────────────
n_total     = len(cw26)
n_exact     = (cw26["match_confidence"] == "exact").sum()
n_fuzzy     = (cw26["match_confidence"] == "fuzzy").sum()
n_unmatched = (cw26["match_confidence"] == "unmatched").sum()

summary_lines = []
summary_lines.append("# 2026_collector Crosswalk — Match Summary")
summary_lines.append(f"Run date: {pd.Timestamp.now().date()}")
summary_lines.append("")
summary_lines.append("## Match Rate (2026_collector era)")
summary_lines.append(f"| Confidence | N | % |")
summary_lines.append(f"|---|---|---|")
summary_lines.append(f"| exact      | {n_exact} | {n_exact/n_total*100:.1f}% |")
summary_lines.append(f"| fuzzy      | {n_fuzzy} | {n_fuzzy/n_total*100:.1f}% |")
summary_lines.append(f"| unmatched  | {n_unmatched} | {n_unmatched/n_total*100:.1f}% |")
summary_lines.append(f"| **total**  | {n_total} | 100% |")
summary_lines.append("")
summary_lines.append(f"## Side Assignment")
summary_lines.append(f"| Method | N |")
summary_lines.append(f"|---|---|")
summary_lines.append(f"| named_outcome | {n_named} |")
summary_lines.append(f"| fallback      | {n_fallback} |")
summary_lines.append("")

print("\n" + "="*65)
print("2026_COLLECTOR CROSSWALK — MATCH SUMMARY")
print("="*65)
print(f"Kalshi KXUFCFIGHT fights (2026):  {n_total}")
print(f"  exact:     {n_exact:>3}  ({n_exact/n_total*100:.1f}%)")
print(f"  fuzzy:     {n_fuzzy:>3}  ({n_fuzzy/n_total*100:.1f}%)")
print(f"  unmatched: {n_unmatched:>3}  ({n_unmatched/n_total*100:.1f}%)")
print(f"Side assignment — named_outcome: {n_named}, fallback: {n_fallback}")

print("\n-- FUZZY MATCHES (manual review) --")
summary_lines.append("## Fuzzy Matches (manual review)")
fuz = cw26[cw26["match_confidence"] == "fuzzy"]
if fuz.empty:
    print("  (none)")
    summary_lines.append("(none)")
else:
    for _, r in fuz.iterrows():
        k_names  = ", ".join(r["fighters_kalshi"] or [])
        pm_names = ", ".join(r["fighters_pm"] or []) if r["fighters_pm"] else "?"
        line = f"  {r['event_date'].date()}  K=[{k_names}]  PM=[{pm_names}]  slug={r['pm_slug']}"
        print(line)
        summary_lines.append(f"- {r['event_date'].date()}  K=[{k_names}]  PM=[{pm_names}]  slug={r['pm_slug']}")

print("\n-- UNMATCHED KALSHI FIGHTS --")
summary_lines.append("")
summary_lines.append("## Unmatched Kalshi Fights")
unm = cw26[cw26["match_confidence"] == "unmatched"]
if unm.empty:
    print("  (none)")
    summary_lines.append("(none)")
else:
    for _, r in unm.iterrows():
        k_names = ", ".join(r["fighters_kalshi"] or [])
        line = f"  {r['event_date'].date()}  [{k_names}]  tickers={r['tickers']}"
        print(line)
        summary_lines.append(f"- {r['event_date'].date()}  [{k_names}]  tickers={json.dumps(r['tickers'])}")

print("\n-- TOP 20 EXACT MATCHES (by Kalshi volume) --")
summary_lines.append("")
summary_lines.append("## Top 20 Exact Matches (by Kalshi volume)")
top_exact = cw26[cw26["match_confidence"] == "exact"].nlargest(20, "kalshi_volume")
for _, r in top_exact.iterrows():
    k = ", ".join(r["fighters_kalshi"] or [])
    pm = r["pm_slug"] or ""
    line = f"  {r['event_date'].date()}  [{k}]  vol={r['kalshi_volume']:,.0f}  slug={pm}"
    print(line)
    summary_lines.append(f"- {r['event_date'].date()}  [{k}]  vol={r['kalshi_volume']:,.0f}  slug={pm}")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 7 — MAD validation: top-5 2026 fights, final 24h
# ─────────────────────────────────────────────────────────────────────────────
print("\n[stage7] MAD validation — top-5 2026 fights (final 24h)...")
summary_lines.append("")
summary_lines.append("## MAD Validation — Top-5 2026 Fights (final 24h)")
summary_lines.append("| Fight | Date | MAD | Flag |")
summary_lines.append("|---|---|---|---|")

# Top-5 by PM trade count (kalshi_volume from API is 0 for closed markets)
matched26 = cw26[(cw26["match_confidence"] == "exact") & cw26["pm_id"].notna()].copy()
top5 = matched26.nlargest(5, "pm_volume")

if top5.empty:
    print("  No exact matches for MAD validation.")
else:
    # Load PM trades once (filter to top-5 condition_ids)
    top5_cids = set(top5["pm_id"].tolist())
    pmg_full = pd.read_parquet(PM_TRADES, columns=["condition_id","timestamp","price_yes"])
    pmg_full["timestamp"] = pd.to_datetime(pmg_full["timestamp"], utc=True)
    pm_top5 = pmg_full[pmg_full["condition_id"].isin(top5_cids)]

    for i, (_, fight) in enumerate(top5.iterrows(), 1):
        pm_id    = fight["pm_id"]
        tickers  = fight["tickers"] or []
        k_names  = fight["fighters_kalshi"] or []
        pm_names = fight["fighters_pm"]     or k_names
        slug     = fight["pm_slug"] or ""

        # Fight time: use Kalshi close_time − 60 min (same convention as panel build)
        # Look up close_time from kf (not stored in cw26 rows)
        kf_row = kf[kf["fight_id"] == fight["fight_id"]]
        close_raw = kf_row.iloc[0]["close_time_raw"] if not kf_row.empty else ""
        try:
            fight_dt = pd.Timestamp(close_raw, tz="UTC") - pd.Timedelta(minutes=60)
            if pd.isna(fight_dt):
                raise ValueError("NaT")
        except Exception:
            # Fallback: event_date at 23:00 UTC (typical UFC main card time)
            fight_dt = fight["event_date"].tz_localize("UTC") + pd.Timedelta(hours=23)

        t_end   = fight_dt
        t_start = fight_dt - pd.Timedelta(hours=24)

        # PM trace: pick the YES-aligned outcome (outcomes[0])
        pm_fight = pm_top5[pm_top5["condition_id"] == pm_id].copy()
        pm_fight = pm_fight[
            (pm_fight["timestamp"] >= t_start) & (pm_fight["timestamp"] <= t_end)
        ].sort_values("timestamp")

        # Kalshi trace: glob collector files for each ticker in the fight
        k_chunks = []
        for ticker in tickers:
            ticker_safe = ticker.replace("*", "")
            pattern = str(LIVE_DIR / "**" / f"trades_{ticker_safe}_*.parquet")
            for fpath in glob.glob(pattern, recursive=True):
                try:
                    chunk = pd.read_parquet(fpath, columns=["created_time","yes_price_dollars","ticker"])
                    chunk["yes_price_dollars"] = pd.to_numeric(chunk["yes_price_dollars"], errors="coerce")
                    k_chunks.append(chunk)
                except Exception:
                    pass

        k_fight_all = pd.concat(k_chunks, ignore_index=True) if k_chunks else pd.DataFrame(
            columns=["created_time","yes_price_dollars","ticker"]
        )

        if not k_fight_all.empty:
            k_fight_all["created_time"] = pd.to_datetime(k_fight_all["created_time"], utc=True, errors="coerce")
            k_fight_all = k_fight_all.dropna(subset=["created_time"])

        # Choose Kalshi ticker corresponding to PM outcomes[0] (named_outcome method)
        pm_yes_name = norm_name(pm_names[0]) if pm_names else ""
        pm_yes_snames = surnames(pm_names[0]) if pm_names else set()

        best_kticker = None
        best_score   = 0
        for t in tickers:
            parsed = parse_kalshi_ticker(t)
            if not parsed:
                continue
            _, _, fcode = parsed
            # Find member with this fighter_code
            fight_entity = kf[kf["fight_id"] == fight["fight_id"]]
            if fight_entity.empty:
                continue
            members = fight_entity.iloc[0]["members"]
            for mem in members:
                if mem["fighter_code"] == fcode:
                    fn_snames = surnames(mem["full_name"])
                    score = len(fn_snames & pm_yes_snames)
                    if score > best_score:
                        best_score = score
                        best_kticker = t
                    break

        if best_kticker is None and tickers:
            best_kticker = tickers[0]

        k_yes = pd.DataFrame()
        if not k_fight_all.empty and best_kticker:
            k_yes = k_fight_all[k_fight_all["ticker"] == best_kticker].copy()
            k_yes = k_yes[
                (k_yes["created_time"] >= t_start) & (k_yes["created_time"] <= t_end)
            ].sort_values("created_time")
            # yes_price_dollars is already in [0,1] scale from collector
            k_yes = k_yes.rename(columns={"yes_price_dollars":"price","created_time":"ts"})

        # Resample to 5-min last
        def resample5(df, tcol, pcol):
            if df.empty:
                return pd.DataFrame(columns=[tcol, pcol])
            s = df.set_index(tcol)[pcol].resample("5min").last().dropna()
            return s.reset_index()

        k_rs  = resample5(k_yes,    "ts",       "price")
        pm_rs = resample5(pm_fight, "timestamp", "price_yes")

        mad_val = None
        if not k_rs.empty and not pm_rs.empty:
            pm_interp = np.interp(
                k_rs["ts"].astype("int64"),
                pm_rs["timestamp"].astype("int64"),
                pm_rs["price_yes"],
            )
            mad_val = float(np.abs(pm_interp - k_rs["price"].values).mean())

        flag = ""
        if mad_val is not None:
            flag = " *** DIVERGES" if mad_val > 0.10 else ""
            mad_str = f"{mad_val:.3f}"
        else:
            mad_str = "n/a (insufficient data)"

        fight_label = " vs ".join(k_names)
        print(f"  [{i}] {fight['event_date'].date()}  {fight_label}")
        print(f"       MAD={mad_str}  Kalshi={len(k_yes):,} trades  PM={len(pm_fight):,} trades  {flag}")
        summary_lines.append(f"| {fight_label} | {fight['event_date'].date()} | {mad_str} | {flag.strip()} |")

        # Validation plot
        fig, ax = plt.subplots(figsize=(12, 5))
        fighter_yes = pm_names[0] if pm_names else "Fighter A"
        if not pm_rs.empty:
            ax.step(pm_rs["timestamp"], pm_rs["price_yes"],
                    where="post", color="#2196F3", linewidth=1.5,
                    label=f"Polymarket P({fighter_yes})", alpha=0.9)
        if not k_rs.empty:
            ax.step(k_rs["ts"], k_rs["price"],
                    where="post", color="#F44336", linewidth=1.5, linestyle="--",
                    label=f"Kalshi P({fighter_yes})", alpha=0.9)
        ax.axhline(0.5, color="grey", linewidth=0.7, linestyle=":")
        if not pd.isna(fight_dt):
            ax.axvline(fight_dt, color="black", linewidth=1.2, linestyle="-", alpha=0.5,
                       label="Kalshi close - 60min")
        ax.set_ylim(-0.02, 1.02)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
        fig.autofmt_xdate(rotation=0, ha="center")
        ax.set_title(
            f"#{i} {fight['event_date'].date()}  {fight_label}\n"
            f"PM: {len(pm_fight):,} trades  |  Kalshi: {len(k_yes):,} trades  |  MAD={mad_str}  |  slug: {slug}",
            fontsize=10
        )
        ax.set_xlabel("UTC (final 24h before Kalshi close)")
        ax.set_ylabel(f"P({fighter_yes})")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        safe = re.sub(r"[^\w\-]", "_", f"{fight['event_date'].date()}_{fight['fight_id'].split('_')[-1]}")
        out_path = VAL_DIR / f"val2026_{i:02d}_{safe}.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"       -> {out_path.name}")

# ─────────────────────────────────────────────────────────────────────────────
# Save QA markdown
# ─────────────────────────────────────────────────────────────────────────────
QA_MD.write_text("\n".join(summary_lines), encoding="utf-8")
print(f"\n[done] QA summary -> {QA_MD}")
print(f"       Crosswalk  -> {OUT_CW}  ({len(combined)} rows total)")
print("\nSTOP — review fuzzy/unmatched before panel build.")
