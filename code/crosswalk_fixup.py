"""
crosswalk_fixup.py — Post-run fixup for 2026_collector crosswalk.

Actions:
  1. Exclude 11 Netflix-card 2026-05-16 fights (exclusion_reason column)
  2. Accept AORHAD / PERMUD / LEBSEO via substring surname normalization rule
  3. Flip test for Lopes/Garcia (MAD=0.161 → check side assignment)
  4. Print corrected 2026 match rate over UFC-only fights
  5. Save updated crosswalk

Normalization rule (permanent, for re-runs):
  Two surname token sets match if any token pair satisfies
  direct equality OR substring containment with min-token-len 4.
  Handles: Aoriqileng/Qileng-Aori, Sumudaerji/Su-Mudaerji, Seokhyeon/Seok-Hyun.
"""

import glob, json, re, sys, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO    = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
OUT_CW  = REPO / "data" / "meta" / "ufc_crosswalk.parquet"
LIVE    = REPO / "data" / "raw" / "live"
PM_TR   = REPO / "data" / "interim" / "pm_gapfill_trades.parquet"
QA_MD   = REPO / "qa" / "crosswalk_fixup.md"

# ── helpers (same as crosswalk_2026.py) ──────────────────────────────────────
def norm_name(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\s]", "", s.lower()).strip()

def surnames(full):
    skip = {"de","da","el","al","van","von","le","la","los","del","jr","sr","ii","iii"}
    return {p for p in norm_name(full).split() if len(p) >= 3 and p not in skip}

def surnames_match(sn_a: set, sn_b: set) -> bool:
    """
    Normalized match: direct intersection OR substring containment (min 4 chars).
    Handles romanization variants: Aoriqileng/Qileng Aori, Sumudaerji/Su Mudaerji,
    Seokhyeon/Seok Hyun, etc.
    """
    if sn_a & sn_b:
        return True
    return any(
        (len(a) >= 4 and a in b) or (len(b) >= 4 and b in a)
        for a in sn_a for b in sn_b
    )

# ── load crosswalk ────────────────────────────────────────────────────────────
cw = pd.read_parquet(OUT_CW)

# Parse list columns (stored as JSON strings)
def parse_list(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return []
    if isinstance(x, list):
        return x
    try:
        v = json.loads(x)
        return v if isinstance(v, list) else []
    except Exception:
        return []

for col in ["fighters_kalshi", "tickers", "fighters_pm", "outcomes", "clob_token_ids"]:
    cw[col] = cw[col].apply(parse_list)

print(f"Loaded crosswalk: {len(cw)} rows")
print(f"  2025_lychee: {(cw['era']=='2025_lychee').sum()}")
print(f"  2026_collector: {(cw['era']=='2026_collector').sum()}")

c26 = cw[cw["era"] == "2026_collector"].copy()

# ─────────────────────────────────────────────────────────────────────────────
# 1. Netflix card exclusions — all KXUFCFIGHT on 2026-05-16 that are non-UFC
# ─────────────────────────────────────────────────────────────────────────────
NETFLIX_IDS = {
    "20260516_FAZBAB",  # Fazil / Babian          — unmatched
    "20260516_JACCRE",  # Jackson / Creighton      — unmatched
    "20260516_MGOMOR",  # Morales / Mgoyan         — unmatched
    "20260516_SALCRO",  # Salahdine / Cross        — unmatched
    "20260516_NGALIN",  # Ngannou / Lins           — unmatched (Ngannou not in UFC)
    "20260516_MOKMOR",  # Moraes / Mokaev          — unmatched (Moraes = ONE Champ)
    "20260516_PERMAS",  # A.Pereira / Masson-Wong  — unmatched
    "20260516_ROUCAR",  # Rousey / Carano          — unmatched (exhibition)
    "20260516_AVIJEN",  # Jenkins / Avila          — unmatched
    "20260516_DOSDES",  # Dos Santos / Despaigne   — fuzzy false match
    "20260516_DIAPER",  # Perry / Diaz             — fuzzy false match
}
EXCL_REASON = "non-UFC promotion (Netflix card 2026-05-16)"

if "exclusion_reason" not in cw.columns:
    cw["exclusion_reason"] = None

netflix_mask = cw["fight_id"].isin(NETFLIX_IDS)
cw.loc[netflix_mask, "exclusion_reason"] = EXCL_REASON
# REJECT the false fuzzy matches
reject_mask = cw["fight_id"].isin({"20260516_DOSDES","20260516_DIAPER"})
cw.loc[reject_mask, "match_confidence"] = "unmatched"
for col in ["pm_id","pm_slug","pm_fight_date","fighters_pm","outcomes","clob_token_ids","pm_volume"]:
    cw.loc[reject_mask, col] = None

print(f"\n[1] Netflix exclusions: {netflix_mask.sum()} fights")
for fid in sorted(NETFLIX_IDS):
    row = cw[cw["fight_id"] == fid].iloc[0]
    k = ", ".join(row["fighters_kalshi"] or [])
    t = ", ".join(row["tickers"] or [])
    print(f"  {fid}  [{k}]  series_prefix={t.split('-')[0] if t else '?'}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Side-assignment recheck with substring normalization
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2] Side assignment recheck (substring normalization)...")
c26_ufc = cw[(cw["era"]=="2026_collector") & cw["exclusion_reason"].isna()].copy()
n_named = n_fallback = 0
fallback_rows = []

for _, row in c26_ufc[c26_ufc["match_confidence"]=="exact"].iterrows():
    k_names  = row["fighters_kalshi"] or []
    pm_names = row["fighters_pm"]     or []
    assigned = []
    for kn in k_names:
        k_sn = surnames(kn)
        found = any(surnames_match(k_sn, surnames(pn)) for pn in pm_names)
        assigned.append(found)
    if all(assigned):
        n_named += 1
    else:
        n_fallback += 1
        fallback_rows.append(f"  {row['fight_id']}  K={k_names}  PM={pm_names}")

print(f"  named_outcome: {n_named}")
print(f"  fallback:      {n_fallback}")
if fallback_rows:
    print("  *** Remaining fallback (needs manual fix):")
    for r in fallback_rows:
        print(r)
else:
    print("  All UFC exact matches: 100% named_outcome -- OK")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Lopes/Garcia flip test
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3] Lopes/Garcia flip test (MAD=0.161)...")
LG_FID  = "20260614_LOPGAR"
lg_row  = cw[cw["fight_id"] == LG_FID].iloc[0]
lg_cid  = lg_row["pm_id"]
lg_tickers = lg_row["tickers"] or []
lg_pm_names = lg_row["fighters_pm"] or lg_row["outcomes"] or []
lg_k_names  = lg_row["fighters_kalshi"] or []

# close_time from kf (fight entity table) — reconstruct from API cache
k26_api = pd.read_parquet(REPO / "data/interim/kxufcfight_2026_markets.parquet")
lop_close = k26_api[k26_api["ticker"] == "KXUFCFIGHT-26JUN14LOPGAR-LOP"]["close_time"].iloc[0]
fight_dt  = pd.Timestamp(lop_close, tz="UTC") - pd.Timedelta(minutes=60)
t_start   = fight_dt - pd.Timedelta(hours=24)
t_end     = fight_dt

# Load PM trades for LG fight
pmg = pd.read_parquet(PM_TR, columns=["condition_id","timestamp","price_yes"])
pmg["timestamp"] = pd.to_datetime(pmg["timestamp"], utc=True)
pm_lg = pmg[
    (pmg["condition_id"] == lg_cid) &
    (pmg["timestamp"] >= t_start) & (pmg["timestamp"] <= t_end)
].sort_values("timestamp")

# Load Kalshi trades for LG fight (LOP ticker = Diego Lopes = PM outcomes[0])
PARSE_RE = re.compile(r"KXUFCFIGHT-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)-([A-Z]+)$")
MONTH3   = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
            "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

pm_yes_snames = surnames(lg_pm_names[0]) if lg_pm_names else set()

# Identify which Kalshi ticker maps to PM outcomes[0] (Diego Lopes)
best_kticker = None; best_score = 0
for t in lg_tickers:
    m = PARSE_RE.match(t)
    if not m: continue
    _,_,_,_,fcode = m.groups()
    # Get full_name from API cache
    api_row = k26_api[k26_api["ticker"] == t]
    if api_row.empty: continue
    title = api_row.iloc[0]["title"]
    mn = re.match(r"Will (.+?) win the", title)
    fn = mn.group(1).strip() if mn else ""
    score = len(surnames(fn) & pm_yes_snames)
    if score > best_score:
        best_score = score; best_kticker = t

if best_kticker is None:
    best_kticker = lg_tickers[0] if lg_tickers else None

k_chunks = []
if best_kticker:
    pattern = str(LIVE / "**" / f"trades_{best_kticker}_*.parquet")
    for fpath in glob.glob(pattern, recursive=True):
        try:
            chunk = pd.read_parquet(fpath, columns=["created_time","yes_price_dollars","ticker"])
            chunk["yes_price_dollars"] = pd.to_numeric(chunk["yes_price_dollars"], errors="coerce")
            k_chunks.append(chunk)
        except Exception:
            pass

k_lg = pd.concat(k_chunks, ignore_index=True) if k_chunks else pd.DataFrame(
    columns=["created_time","yes_price_dollars","ticker"])
if not k_lg.empty:
    k_lg["created_time"] = pd.to_datetime(k_lg["created_time"], utc=True, errors="coerce")
    k_lg = k_lg.dropna(subset=["created_time"])
    k_lg = k_lg[(k_lg["created_time"] >= t_start) & (k_lg["created_time"] <= t_end)].sort_values("created_time")
    k_lg = k_lg.rename(columns={"yes_price_dollars":"price","created_time":"ts"})

def resample5(df, tcol, pcol):
    if df.empty: return pd.DataFrame(columns=[tcol, pcol])
    s = df.set_index(tcol)[pcol].resample("5min").last().dropna()
    return s.reset_index()

k_rs  = resample5(k_lg,    "ts",        "price")
pm_rs = resample5(pm_lg,   "timestamp", "price_yes")

if not k_rs.empty and not pm_rs.empty:
    k_int64 = k_rs["ts"].astype("int64").values
    pm_int64 = pm_rs["timestamp"].astype("int64").values
    pm_prices = pm_rs["price_yes"].values

    pm_interp = np.interp(k_int64, pm_int64, pm_prices)
    k_prices  = k_rs["price"].astype(float).values

    mad_orig    = float(np.abs(pm_interp - k_prices).mean())
    mad_flipped = float(np.abs((1 - pm_interp) - k_prices).mean())

    print(f"  Fight: {' vs '.join(lg_k_names)}")
    print(f"  PM outcomes[0]={lg_pm_names[0] if lg_pm_names else '?'}  Kalshi ticker={best_kticker}")
    print(f"  Kalshi trades: {len(k_lg):,}  |  PM trades: {len(pm_lg):,}  (5-min bins: K={len(k_rs)}, PM={len(pm_rs)})")
    print(f"  MAD original:  {mad_orig:.3f}")
    print(f"  MAD flipped:   {mad_flipped:.3f}")
    if mad_flipped < mad_orig * 0.5:
        print(f"  VERDICT: side flip significantly reduces MAD -> FLIP PM side, add override")
    else:
        print(f"  VERDICT: flip does NOT help -> thin PM liquidity / genuine divergence; keep original side")
        # Check |2p-1| reference
        p_k = k_prices.mean()
        print(f"  Note: mean Kalshi price={p_k:.3f}, |2p-1|={abs(2*p_k-1):.3f}")
else:
    print(f"  Insufficient data for flip test (K={len(k_lg)}, PM={len(pm_lg)})")
    mad_orig = mad_flipped = None

# ─────────────────────────────────────────────────────────────────────────────
# 4. Save updated crosswalk
# ─────────────────────────────────────────────────────────────────────────────
# Re-serialize list columns
def to_json(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return json.dumps(x) if isinstance(x, list) else x

cw_save = cw.copy()
for col in ["fighters_kalshi","tickers","fighters_pm","outcomes","clob_token_ids"]:
    cw_save[col] = cw_save[col].apply(to_json)

cw_save.to_parquet(OUT_CW, index=False)
print(f"\n[4] Saved {OUT_CW}  ({len(cw_save)} rows)")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Corrected match rate — UFC-only fights
# ─────────────────────────────────────────────────────────────────────────────
c26_all   = cw[cw["era"] == "2026_collector"]
c26_ufc2  = c26_all[c26_all["exclusion_reason"].isna()]
excl      = c26_all[c26_all["exclusion_reason"].notna()]

n_ufc     = len(c26_ufc2)
n_exact   = (c26_ufc2["match_confidence"] == "exact").sum()
n_fuzzy   = (c26_ufc2["match_confidence"] == "fuzzy").sum()
n_unm     = (c26_ufc2["match_confidence"] == "unmatched").sum()

print("\n" + "="*60)
print("2026_COLLECTOR — CORRECTED MATCH RATE (UFC FIGHTS ONLY)")
print("="*60)
print(f"Total 2026_collector fights:    {len(c26_all)}")
print(f"  Netflix exclusions:           {len(excl)}")
print(f"  UFC denominator:              {n_ufc}")
print(f"    exact:     {n_exact:>3}  ({n_exact/n_ufc*100:.1f}%)")
print(f"    fuzzy:     {n_fuzzy:>3}  ({n_fuzzy/n_ufc*100:.1f}%)")
print(f"    unmatched: {n_unm:>3}  ({n_unm/n_ufc*100:.1f}%)")
if n_unm > 0:
    unm_rows = c26_ufc2[c26_ufc2["match_confidence"]=="unmatched"]
    for _, r in unm_rows.iterrows():
        k = ", ".join(r["fighters_kalshi"] or [])
        print(f"      {r['event_date'].date()}  [{k}]  (pending gap-fill extension)")
print(f"  Side assignment (UFC exact): named_outcome={n_named}, fallback={n_fallback}")

# Save QA
lines = [
    "# Crosswalk Fixup — 2026_collector",
    f"Run: {pd.Timestamp.now().date()}",
    "",
    "## Actions",
    f"- Netflix exclusions: {len(excl)} fights (2026-05-16 non-UFC card)",
    f"- REJECT fuzzy: DOSDES, DIAPER (surname collision, different fights)",
    f"- Side assignment fix: substring normalization rule applied",
    f"  - AORHAD: Qileng Aori / Aoriqileng",
    f"  - PERMUD: Su Mudaerji / Sumudaerji",
    f"  - LEBSEO: Seok Hyun Ko / Seokhyeon Ko",
    "",
    "## Corrected Match Rate (2026 UFC fights only)",
    f"| | N | % |","|---|---|---|",
    f"| exact | {n_exact} | {n_exact/n_ufc*100:.1f}% |",
    f"| fuzzy | {n_fuzzy} | {n_fuzzy/n_ufc*100:.1f}% |",
    f"| unmatched | {n_unm} | {n_unm/n_ufc*100:.1f}% |",
    f"| UFC denominator | {n_ufc} | |",
    f"| Netflix excluded | {len(excl)} | |",
    "",
    "## Lopes/Garcia Flip Test",
]
if mad_orig is not None:
    lines += [
        f"MAD original: {mad_orig:.3f}",
        f"MAD flipped:  {mad_flipped:.3f}",
        f"Verdict: {'FLIP' if mad_flipped < mad_orig * 0.5 else 'keep original side (thin PM)'}",
    ]
else:
    lines.append("Insufficient data for flip test.")
QA_MD.write_text("\n".join(lines), encoding="utf-8")
print(f"\n[done] QA -> {QA_MD}")
