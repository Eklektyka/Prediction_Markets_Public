"""
bare_slug_side_audit.py — Side-mapping audit for bare-slug-resolved crosswalk entries

For every bare-slug-resolved fight:
  • Confirm side is assigned by named PM outcome matched to Kalshi fighter name,
    never by slug position alone.
For the top-10 bare-slug fights by Kalshi volume (+ Ko/Goff):
  • Scan archive for PM token trades, join timestamps, compute price_yes.
  • Scan Kalshi trades for the YES-side ticker.
  • Compute MAD over the final 24 h window.
  • Flag MAD > 0.10 (flipped side shows as |2p-1|, unmistakable).
Output:
  • qa/crosswalk_validation/bare_slug_audit.csv
  • Promotes Ko/Goff to exact in crosswalk_overrides.csv if MAD <= 0.10
"""

import io, json, re, subprocess, sys, tarfile, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── paths ─────────────────────────────────────────────────────────────────────
REPO     = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
LYCHEE   = Path(r"C:\Kalshi_data\lychee")
EXTRACT  = LYCHEE / "extracted" / "data"

OUT_CROSSWALK = REPO / "data" / "meta" / "ufc_crosswalk.parquet"
OUT_OVERRIDES = REPO / "data" / "meta" / "crosswalk_overrides.csv"
OUT_BLOCKS    = REPO / "data" / "meta" / "polygon_blocks.parquet"
OUT_VAL_DIR   = LYCHEE / "qa" / "crosswalk_validation"
OUT_VAL_DIR.mkdir(parents=True, exist_ok=True)

K_MARKETS_DIR = EXTRACT / "kalshi" / "markets"
K_TRADES_DIR  = EXTRACT / "kalshi" / "trades"
ARCHIVE       = LYCHEE / "data.tar.zst"

ZSTD = (r"C:\Users\micha\AppData\Local\Microsoft\WinGet\Packages"
        r"\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe"
        r"\poppler-25.07.0\Library\bin\zstd.exe")

# ── helpers ───────────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\s]", "", s.lower()).strip()

def name_overlap(a: str, b: str) -> int:
    return len(set(norm(a).split()) & set(norm(b).split()))

# ── 1. Load crosswalk ─────────────────────────────────────────────────────────
print("[1] loading crosswalk...")
cw = pd.read_parquet(OUT_CROSSWALK)

list_cols = ["fighters_kalshi", "tickers", "fighters_pm", "outcomes", "clob_token_ids"]
for col in list_cols:
    cw[col] = cw[col].apply(
        lambda x: json.loads(x) if isinstance(x, str) and x else
                  (x if isinstance(x, list) else [])
    )

# Bare-slug-resolved: matched but pm_slug has no "ufc" or "mma"
matched = cw[cw["pm_id"].notna()].copy()
bare = matched[~matched["pm_slug"].str.contains("ufc|mma", case=False, na=False)].copy()
print(f"  {len(matched)} total matched fights")
print(f"  {len(bare)} bare-slug-resolved fights (no ufc/mma in pm_slug)")

# ── 2. Build ticker → fighter name from Kalshi markets ────────────────────────
print("\n[2] building ticker->name map...")
ticker_to_name: dict[str, str] = {}
for f in sorted(K_MARKETS_DIR.glob("*.parquet")):
    df = pd.read_parquet(f, columns=["ticker", "title"])
    for _, row in df[df["ticker"].str.startswith("KXUFC", na=False)].iterrows():
        m = re.match(r"Will (.+?) win the .+ vs .+ professional MMA", row["title"])
        if m:
            ticker_to_name[row["ticker"]] = m.group(1).strip()
print(f"  {len(ticker_to_name)} ticker->name entries")

# ── 3. Side-mapping audit for all bare-slug fights ───────────────────────────
print("\n[3] auditing side assignments for all bare-slug fights...")

audit_rows = []
for _, fight in bare.iterrows():
    outcomes   = fight["outcomes"]   or []
    tickers    = fight["tickers"]    or []
    fighters_k = fight["fighters_kalshi"] or []
    fighters_p = fight["fighters_pm"] or []

    # Named PM outcomes are any outcome not "yes"/"no"
    named_outcomes = [o for o in outcomes if o.lower() not in ("yes", "no")]
    side_method = "named_outcome" if named_outcomes else "slug_position"

    # PM YES fighter = fighters_pm[0] (derived from named outcomes or slug in that order)
    pm_yes_name = fighters_p[0] if fighters_p else (outcomes[0] if outcomes else "")

    # Find Kalshi ticker whose fighter name best overlaps with pm_yes_name
    best_ticker, best_score = (tickers[0] if tickers else ""), -1
    for t in tickers:
        kname = ticker_to_name.get(t, "")
        sc = name_overlap(pm_yes_name, kname)
        if sc > best_score:
            best_score = sc
            best_ticker = t

    k_yes_name = ticker_to_name.get(best_ticker, "?")

    audit_rows.append({
        "fight_id":       fight["fight_id"],
        "event_date":     fight["event_date"].date(),
        "pm_slug":        fight["pm_slug"],
        "fighters_kalshi": ", ".join(fighters_k),
        "pm_yes_outcome": pm_yes_name,
        "k_yes_ticker":   best_ticker,
        "k_yes_name":     k_yes_name,
        "side_method":    side_method,
        "name_score":     best_score,
        "kalshi_volume":  fight["kalshi_volume"],
        "pm_id":          str(fight["pm_id"]),
        "clob_token_ids": fight["clob_token_ids"],
        "match_confidence": fight["match_confidence"],
    })

audit_df = pd.DataFrame(audit_rows)

print(f"\n  Side assignment methods:")
for method, cnt in audit_df["side_method"].value_counts().items():
    print(f"    {method}: {cnt}")

low_score = audit_df[audit_df["name_score"] == 0]
if low_score.empty:
    print("  All bare-slug fights have name_score >= 1 (no zero-score mappings)")
else:
    print(f"\n  WARNING: {len(low_score)} fights with name_score=0 (slug-position fallback):")
    for _, r in low_score.iterrows():
        print(f"    {r['event_date']}  slug={r['pm_slug']}  pm_yes={r['pm_yes_outcome']}  k_yes={r['k_yes_name']}")

# ── 4. Select fights to compute MAD for ──────────────────────────────────────
# Top-10 by kalshi_volume + Ko/Goff (if not already in top-10)
top10 = audit_df.nlargest(10, "kalshi_volume").copy()
kogof_mask = audit_df["pm_slug"] == "goff-vs-ko"
kogof_extra = audit_df[kogof_mask & ~audit_df["fight_id"].isin(top10["fight_id"])]
mad_targets = pd.concat([top10, kogof_extra], ignore_index=True)
print(f"\n[4] MAD targets: {len(mad_targets)} fights")
for _, r in mad_targets.iterrows():
    print(f"    {r['event_date']}  {r['pm_slug']}  k_vol={r['kalshi_volume']:,}")

# ── 5. Collect bare-slug token IDs for archive scan ──────────────────────────
# Build token_to_meta for these markets (YES=idx0, NO=idx1 per clob_token_ids)
token_to_meta: dict[str, dict] = {}
for _, r in mad_targets.iterrows():
    mid   = r["pm_id"]
    tids  = r["clob_token_ids"]
    for idx, tid in enumerate(tids):
        token_to_meta[str(tid)] = {
            "market_id":     mid,
            "outcome_index": idx,  # 0=YES, 1=NO
        }

bare_token_set = set(token_to_meta.keys())
print(f"\n  {len(bare_token_set)} outcome tokens to scan for")

# ── 6. Stream-scan archive for those PM trades ────────────────────────────────
print("\n[5] scanning archive for bare-slug PM trades...")
token_arr = pa.array(list(bare_token_set), type=pa.string())

pm_chunks = []
files_scanned = files_hit = 0

zproc = subprocess.Popen(
    [ZSTD, "-d", str(ARCHIVE), "--stdout"],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
)
with tarfile.open(fileobj=zproc.stdout, mode="r|") as tf:
    for member in tf:
        if not (member.name.startswith("data/polymarket/trades/")
                and member.name.endswith(".parquet")
                and "/._" not in member.name
                and not Path(member.name).name.startswith("._")):
            continue
        fobj = tf.extractfile(member)
        if fobj is None:
            continue
        data = fobj.read()
        files_scanned += 1
        if files_scanned % 5000 == 0:
            print(f"  scanned {files_scanned:,} trade files, {files_hit:,} hits...")
        try:
            tbl = pq.read_table(
                io.BytesIO(data),
                columns=["block_number", "maker_asset_id", "taker_asset_id",
                         "maker_amount", "taker_amount"]
            )
        except Exception:
            continue
        mask = pc.or_(
            pc.is_in(tbl.column("maker_asset_id"), value_set=token_arr),
            pc.is_in(tbl.column("taker_asset_id"), value_set=token_arr),
        )
        hits = tbl.filter(mask)
        if hits.num_rows > 0:
            files_hit += 1
            pm_chunks.append(hits.to_pandas())

zproc.wait()
print(f"  done: scanned {files_scanned:,} files, {files_hit:,} with bare-slug hits")

if not pm_chunks:
    print("  WARNING: no PM trades found — cannot compute MAD")
    pm_trades = pd.DataFrame(columns=["block_number","maker_asset_id","taker_asset_id",
                                       "maker_amount","taker_amount"])
else:
    pm_trades = pd.concat(pm_chunks, ignore_index=True)
    print(f"  {len(pm_trades):,} raw PM trade rows")

# ── 6b. Compute price_yes and join timestamps ─────────────────────────────────
if len(pm_trades):
    def compute_price(row):
        ma_id = str(row["maker_asset_id"])
        ta_id = str(row["taker_asset_id"])
        ma    = row["maker_amount"]
        ta    = row["taker_amount"]
        if ma_id in token_to_meta:
            meta = token_to_meta[ma_id]
            raw  = ta / ma if ma else np.nan
        elif ta_id in token_to_meta:
            meta = token_to_meta[ta_id]
            raw  = ma / ta if ta else np.nan
        else:
            return np.nan, np.nan, None
        oi        = meta["outcome_index"]
        price_yes = raw if oi == 0 else (1.0 - raw)
        return raw, price_yes, meta["market_id"]

    print("  computing price_yes...")
    res = pm_trades.apply(compute_price, axis=1, result_type="expand")
    res.columns = ["price_raw", "price_yes", "market_id"]
    pm_trades = pd.concat([pm_trades[["block_number"]], res], axis=1)
    pm_trades = pm_trades[pm_trades["price_yes"].between(0, 1)].copy()

    print("  joining block timestamps...")
    blocks = pd.read_parquet(OUT_BLOCKS)
    pm_trades = pm_trades.merge(blocks, on="block_number", how="left")
    pm_trades["ts_utc"] = pd.to_datetime(pm_trades["ts_utc"], utc=True)
    pm_trades = pm_trades.dropna(subset=["ts_utc", "price_yes"])
    print(f"  {len(pm_trades):,} PM trade rows after price filter + timestamp join")

# ── 7. Scan Kalshi trades for YES tickers ─────────────────────────────────────
print("\n[6] scanning Kalshi trades for YES-side tickers...")
yes_tickers = set(mad_targets["k_yes_ticker"].dropna().tolist())
yes_arr = pa.array(list(yes_tickers), type=pa.string())

k_chunks = []
for f in sorted(K_TRADES_DIR.glob("*.parquet")):
    try:
        tbl = pq.read_table(f, columns=["ticker", "yes_price", "created_time"])
        mask = pc.is_in(tbl.column("ticker"), value_set=yes_arr)
        hit = tbl.filter(mask)
        if hit.num_rows > 0:
            k_chunks.append(hit.to_pandas())
    except Exception:
        continue

k_trades = (pd.concat(k_chunks, ignore_index=True) if k_chunks
            else pd.DataFrame(columns=["ticker", "yes_price", "created_time"]))
k_trades["created_time"] = pd.to_datetime(k_trades["created_time"], utc=True)
k_trades["price"] = k_trades["yes_price"] / 100.0
print(f"  {len(k_trades):,} Kalshi trade rows for {len(yes_tickers)} YES tickers")

# ── 8. Compute MAD for each target fight ──────────────────────────────────────
print("\n[7] computing MAD (final 24h window)...")

results = []
for _, r in mad_targets.iterrows():
    fight_dt = pd.Timestamp(r["event_date"]).tz_localize("UTC")
    t_start  = fight_dt - pd.Timedelta(hours=24)
    t_end    = fight_dt + pd.Timedelta(hours=6)

    pm_mid = r["pm_id"]
    k_tkr  = r["k_yes_ticker"]

    # PM: filter by market_id and time window
    if len(pm_trades):
        pm_f = pm_trades[
            (pm_trades["market_id"] == pm_mid) &
            (pm_trades["ts_utc"] >= t_start) &
            (pm_trades["ts_utc"] <= t_end)
        ].sort_values("ts_utc")
    else:
        pm_f = pd.DataFrame()

    # Kalshi: filter by YES ticker and time window
    k_f = k_trades[
        (k_trades["ticker"] == k_tkr) &
        (k_trades["created_time"] >= t_start) &
        (k_trades["created_time"] <= t_end)
    ].sort_values("created_time")

    # Resample both to 5-min last price, then compute MAD on common index
    def resamp(df, tcol, pcol):
        if df.empty:
            return pd.Series(dtype=float)
        return df.set_index(tcol)[pcol].resample("5min").last().ffill().dropna()

    pm_r = resamp(pm_f, "ts_utc",      "price_yes")
    k_r  = resamp(k_f,  "created_time", "price")

    common = pm_r.index.intersection(k_r.index)
    if len(common) >= 3:
        mad = float(np.abs(pm_r.loc[common] - k_r.loc[common]).mean())
    else:
        mad = np.nan

    flag = "FLIPPED?" if (not np.isnan(mad) and mad > 0.10) else ""

    results.append({
        "fight_id":       r["fight_id"],
        "event_date":     r["event_date"],
        "pm_slug":        r["pm_slug"],
        "side_method":    r["side_method"],
        "name_score":     r["name_score"],
        "pm_yes_outcome": r["pm_yes_outcome"],
        "k_yes_name":     r["k_yes_name"],
        "n_pm_5min":      int(len(pm_r)),
        "n_k_5min":       int(len(k_r)),
        "n_common":       int(len(common)),
        "mad_24h":        round(mad, 4) if not np.isnan(mad) else np.nan,
        "flag":           flag,
        "kalshi_volume":  r["kalshi_volume"],
    })

results_df = pd.DataFrame(results).sort_values("kalshi_volume", ascending=False)

# ── 9. Print table ────────────────────────────────────────────────────────────
print()
print("=" * 95)
print("BARE-SLUG SIDE AUDIT — MAD TABLE (top-10 + Ko/Goff, sorted by Kalshi volume)")
print("=" * 95)
hdr = (f"{'fight_id':<22} {'date':<12} {'side_method':<16} {'sc':>3}"
       f" {'pm_yes':<14} {'k_yes':<14} {'n_pm':>5} {'n_k':>5} {'n_com':>6} {'MAD_24h':>8}  flag")
print(hdr)
print("-" * len(hdr))
for _, r in results_df.iterrows():
    mad_s = f"{r['mad_24h']:.4f}" if not np.isnan(r["mad_24h"]) else "  N/A"
    print(
        f"  {r['fight_id']:<20} {str(r['event_date']):<12} {r['side_method']:<16}"
        f" {r['name_score']:>3}"
        f" {str(r['pm_yes_outcome'])[:14]:<14} {str(r['k_yes_name'])[:14]:<14}"
        f" {r['n_pm_5min']:>5} {r['n_k_5min']:>5} {r['n_common']:>6} {mad_s:>8}  {r['flag']}"
    )
print("=" * 95)

# ── 10. Save CSV ──────────────────────────────────────────────────────────────
out_csv = OUT_VAL_DIR / "bare_slug_audit.csv"
results_df.to_csv(out_csv, index=False)
print(f"\nSaved: {out_csv}")

# ── 11. Promote Ko/Goff to exact if it passes ────────────────────────────────
kogof_res = results_df[results_df["pm_slug"] == "goff-vs-ko"]
if kogof_res.empty:
    print("\nKo/Goff not found in MAD targets — check crosswalk.")
else:
    mad_val = kogof_res.iloc[0]["mad_24h"]
    if np.isnan(mad_val):
        print(f"\nKo/Goff: MAD=N/A (insufficient overlapping data) — not promoting.")
    elif mad_val > 0.10:
        print(f"\nKo/Goff: MAD={mad_val:.4f} > 0.10 — SIDE LIKELY FLIPPED, not promoting.")
    else:
        print(f"\nKo/Goff: MAD={mad_val:.4f} <= 0.10 — side confirmed correct. Promoting to exact.")
        # Append ACCEPT to overrides CSV
        ov_path = OUT_OVERRIDES
        ov = pd.read_csv(ov_path, dtype=str).fillna("")
        kogof_fight_id = kogof_res.iloc[0]["fight_id"]
        already = ov[ov["fight_id"] == kogof_fight_id]
        if already.empty:
            new_row = pd.DataFrame([{
                "fight_id":        kogof_fight_id,
                "action":          "ACCEPT",
                "correct_pm_id":   "",
                "note":            (f"Ko/Goff bare-slug match confirmed: MAD={mad_val:.4f} <= 0.10; "
                                    f"named outcomes align to Kalshi fighters"),
            }])
            ov = pd.concat([ov, new_row], ignore_index=True)
            ov.to_csv(ov_path, index=False)
            print(f"  Appended ACCEPT row for {kogof_fight_id} to {ov_path.name}")
        else:
            print(f"  {kogof_fight_id} already in overrides ({already.iloc[0]['action']}) — no change.")

print("\nDone.")
