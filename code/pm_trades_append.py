"""
pm_trades_append.py — Incremental append of missing bare-slug PM trades

Step 1: diff  crosswalk exact-match pm_ids vs market_ids in interim trades
Step 2: scan archive for missing tokens, compute prices identically to pipeline
Step 3: append to data/interim/polymarket_ufc_trades.parquet (dedupe)
Step 4: rebuild data/clean/phase2_prototype_panel.parquet (top-20, same rules)
"""

import io, json, re, subprocess, sys, tarfile, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO   = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
LYCHEE = Path(r"C:\Kalshi_data\lychee")
EXTRACT = LYCHEE / "extracted" / "data"

OUT_CROSSWALK = REPO / "data" / "meta"    / "ufc_crosswalk.parquet"
PM_TRADES     = REPO / "data" / "interim" / "polymarket_ufc_trades.parquet"
OUT_BLOCKS    = REPO / "data" / "meta"    / "polygon_blocks.parquet"
OUT_PANEL     = REPO / "data" / "clean"   / "phase2_prototype_panel.parquet"
ARCHIVE       = LYCHEE / "data.tar.zst"
K_MARKETS_DIR = EXTRACT / "kalshi" / "markets"
K_TRADES_DIR  = EXTRACT / "kalshi" / "trades"

ZSTD = (r"C:\Users\micha\AppData\Local\Microsoft\WinGet\Packages"
        r"\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe"
        r"\poppler-25.07.0\Library\bin\zstd.exe")

# ── helpers (shared with panel builder) ──────────────────────────────────────
def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\s]", "", s.lower()).strip()

def name_overlap(a: str, b: str) -> int:
    return len(set(norm(a).split()) & set(norm(b).split()))

# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 — DIFF
# ═════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("STEP 1: diff crosswalk pm_ids vs interim trades market_ids")
print("=" * 70)

cw = pd.read_parquet(OUT_CROSSWALK)
for col in ["fighters_kalshi", "tickers", "fighters_pm", "clob_token_ids"]:
    cw[col] = cw[col].apply(
        lambda x: json.loads(x) if isinstance(x, str) and x else
                  (x if isinstance(x, list) else [])
    )

exact = cw[cw["match_confidence"] == "exact"].copy()
crosswalk_pm_ids = set(exact["pm_id"].astype(str).tolist())

pm_existing = pd.read_parquet(PM_TRADES, columns=["market_id"])
pm_existing_ids = set(pm_existing["market_id"].astype(str).tolist())
del pm_existing

missing_pm_ids = crosswalk_pm_ids - pm_existing_ids
print(f"  Crosswalk exact pm_ids:      {len(crosswalk_pm_ids)}")
print(f"  market_ids in interim trades: {len(pm_existing_ids)}")
print(f"  Missing pm_ids:               {len(missing_pm_ids)}")

# Get details for missing markets
missing_rows = exact[exact["pm_id"].astype(str).isin(missing_pm_ids)].copy()
missing_rows["pm_id"] = missing_rows["pm_id"].astype(str)

# Build token_to_meta for missing markets
# clob_token_ids[0] = YES token (outcome_index=0), [1] = NO token (outcome_index=1)
token_to_meta: dict[str, dict] = {}
for _, row in missing_rows.iterrows():
    mid  = row["pm_id"]
    slug = row["pm_slug"] or ""
    for idx, tid in enumerate(row["clob_token_ids"]):
        token_to_meta[str(tid)] = {
            "market_id":     mid,
            "slug":          slug,
            "outcome_index": idx,
        }

print(f"\n  Missing markets:")
print(f"  {'fight_id':<22} {'date':<12} {'pm_id':<10} {'pm_slug'}")
print(f"  " + "-" * 70)
for _, r in missing_rows.sort_values("event_date").iterrows():
    k_names = ", ".join(r["fighters_kalshi"])
    print(f"  {r['fight_id']:<22} {str(r['event_date'].date()):<12} "
          f"{r['pm_id']:<10} {r['pm_slug']}")
print(f"\n  {len(token_to_meta)} outcome tokens to scan for "
      f"({len(missing_pm_ids)} markets × 2)")

if not missing_pm_ids:
    print("  Nothing missing — interim file is complete.")
    # Still rebuild panel in case of prior skips
    new_rows_added = 0
else:
    # ═════════════════════════════════════════════════════════════════════════
    # STEP 2 — ARCHIVE SCAN
    # ═════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("STEP 2: scanning archive for missing tokens")
    print("=" * 70)

    missing_arr = pa.array(list(token_to_meta.keys()), type=pa.string())

    raw_chunks = []
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
                print(f"  scanned {files_scanned:,}  hits {files_hit:,}")
            try:
                tbl = pq.read_table(
                    io.BytesIO(data),
                    columns=["block_number", "maker_asset_id", "taker_asset_id",
                             "maker_amount", "taker_amount"]
                )
            except Exception:
                continue
            mask = pc.or_(
                pc.is_in(tbl.column("maker_asset_id"), value_set=missing_arr),
                pc.is_in(tbl.column("taker_asset_id"), value_set=missing_arr),
            )
            hit = tbl.filter(mask)
            if hit.num_rows > 0:
                files_hit += 1
                raw_chunks.append(hit.to_pandas())

    zproc.wait()
    print(f"  done: scanned {files_scanned:,} files  |  {files_hit:,} with hits")

    if not raw_chunks:
        print("  WARNING: no new trades found in archive")
        new_rows_added = 0
    else:
        raw = pd.concat(raw_chunks, ignore_index=True)
        print(f"  {len(raw):,} raw trade rows")

        # Compute price_yes (identical to pipeline Stage 4)
        def compute_price(row):
            ma_id = str(row["maker_asset_id"])
            ta_id = str(row["taker_asset_id"])
            ma    = row["maker_amount"]
            ta    = row["taker_amount"]
            if ma_id in token_to_meta:
                meta = token_to_meta[ma_id]
                raw_p = ta / ma if ma else np.nan
            elif ta_id in token_to_meta:
                meta = token_to_meta[ta_id]
                raw_p = ma / ta if ta else np.nan
            else:
                return np.nan, np.nan, None, None
            oi = meta["outcome_index"]
            price_yes = raw_p if oi == 0 else (1.0 - raw_p)
            return raw_p, price_yes, meta["market_id"], meta["slug"]

        print("  computing price_yes...")
        res = raw.apply(compute_price, axis=1, result_type="expand")
        res.columns = ["price_raw", "price_yes", "market_id", "slug"]
        new_trades = pd.concat([raw, res], axis=1)
        new_trades = new_trades[new_trades["price_yes"].between(0, 1)].copy()
        print(f"  {len(new_trades):,} rows after price_yes filter")

        # Join block timestamps
        print("  joining block timestamps...")
        blocks = pd.read_parquet(OUT_BLOCKS)
        new_trades = new_trades.merge(blocks, on="block_number", how="left")
        new_trades["ts_utc"] = pd.to_datetime(new_trades["ts_utc"], utc=True)
        new_trades = new_trades.dropna(subset=["ts_utc"])
        print(f"  {len(new_trades):,} rows after timestamp join")

        # Print per-market breakdown
        print(f"\n  Rows per missing market:")
        for mid, grp in new_trades.groupby("market_id"):
            slug = grp["slug"].iloc[0]
            mrow = missing_rows[missing_rows["pm_id"] == mid]
            fid = mrow.iloc[0]["fight_id"] if not mrow.empty else "?"
            print(f"    {fid:<22} pm_id={mid:<10} slug={slug}  rows={len(grp):,}")

        # ── STEP 3: APPEND (dedupe on tx composite key) ──────────────────────
        print("\n" + "=" * 70)
        print("STEP 3: appending to interim parquet (deduplication)")
        print("=" * 70)

        DEDUP_COLS = ["block_number", "maker_asset_id", "taker_asset_id",
                      "maker_amount", "taker_amount"]

        existing = pd.read_parquet(PM_TRADES)
        existing["ts_utc"] = pd.to_datetime(existing["ts_utc"], utc=True)

        n_before = len(existing)

        # Ensure column alignment
        col_order = list(existing.columns)
        for c in col_order:
            if c not in new_trades.columns:
                new_trades[c] = np.nan
        new_trades = new_trades[col_order]

        combined = pd.concat([existing, new_trades], ignore_index=True)

        # Dedup: cast dedup cols to same types before dropping
        for c in ["maker_asset_id", "taker_asset_id"]:
            combined[c] = combined[c].astype(str)
        for c in ["block_number", "maker_amount", "taker_amount"]:
            combined[c] = pd.to_numeric(combined[c], errors="coerce")

        combined = combined.drop_duplicates(subset=DEDUP_COLS, keep="first")
        n_after = len(combined)
        new_rows_added = n_after - n_before

        combined.to_parquet(PM_TRADES, index=False)
        print(f"  rows before: {n_before:,}")
        print(f"  new rows added: {new_rows_added:,}")
        print(f"  rows after: {n_after:,}")
        print(f"  saved: {PM_TRADES}")

# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 — REBUILD PANEL
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 4: rebuilding phase2 prototype panel")
print("=" * 70)

BAR_FREQ  = "5min"
MAX_FFILL = 12
WIN_PRE   = 72
WIN_POST  =  4

# -- Ticker->name map ---------------------------------------------------------
ticker_to_name: dict[str, str] = {}
for f in sorted(K_MARKETS_DIR.glob("*.parquet")):
    df = pd.read_parquet(f, columns=["ticker", "title"])
    for _, row in df[df["ticker"].str.startswith("KXUFC", na=False)].iterrows():
        m = re.match(r"Will (.+?) win the .+ vs .+ professional MMA", row["title"])
        if m:
            ticker_to_name[row["ticker"]] = m.group(1).strip()

# -- Top-20 by combined volume ------------------------------------------------
exact["combined_vol"] = exact["kalshi_volume"].fillna(0) + exact["pm_volume"].fillna(0)
top20 = exact.nlargest(20, "combined_vol").reset_index(drop=True)

# -- YES ticker selection per fight -------------------------------------------
fight_meta = []
for _, fight in top20.iterrows():
    tickers    = fight["tickers"]
    fighters_p = (json.loads(fight["fighters_pm"])
                  if isinstance(fight["fighters_pm"], str) else fight["fighters_pm"]) or []
    pm_yes_name = fighters_p[0] if fighters_p else ""

    best_tkr, best_score = (tickers[0] if tickers else ""), -1
    for t in tickers:
        sc = name_overlap(pm_yes_name, ticker_to_name.get(t, ""))
        if sc > best_score:
            best_score = sc
            best_tkr = t

    fight_meta.append({
        "fight_id":    fight["fight_id"],
        "event_date":  fight["event_date"],
        "pm_id":       str(fight["pm_id"]),
        "yes_ticker":  best_tkr,
        "pm_flip":     (best_score == 0 and len(tickers) >= 2),
        "combined_vol": fight["combined_vol"],
        "fighters_k":  fight["fighters_kalshi"],
        "fighters_p":  fighters_p,
    })

fmeta = pd.DataFrame(fight_meta)

# -- Load Kalshi trades -------------------------------------------------------
yes_tickers = set(fmeta["yes_ticker"].dropna().tolist())
yes_arr = pa.array(list(yes_tickers), type=pa.string())
print(f"  scanning Kalshi trades for {len(yes_tickers)} YES tickers...")

k_chunks = []
for f in sorted(K_TRADES_DIR.glob("*.parquet")):
    try:
        tbl = pq.read_table(f, columns=["ticker","yes_price","count","created_time"])
        hit = tbl.filter(pc.is_in(tbl.column("ticker"), value_set=yes_arr))
        if hit.num_rows > 0:
            k_chunks.append(hit.to_pandas())
    except Exception:
        continue

k_all = (pd.concat(k_chunks, ignore_index=True) if k_chunks
         else pd.DataFrame(columns=["ticker","yes_price","count","created_time"]))
k_all["created_time"] = pd.to_datetime(k_all["created_time"], utc=True)
k_all["price"] = k_all["yes_price"] / 100.0
k_all["count"] = pd.to_numeric(k_all["count"], errors="coerce").fillna(1).astype(float)
k_all = k_all.sort_values("created_time")
print(f"  {len(k_all):,} Kalshi trade rows")

# -- Load PM trades -----------------------------------------------------------
pm_ids_needed = set(fmeta["pm_id"].tolist())
pm_all = pd.read_parquet(PM_TRADES)
pm_all["ts_utc"] = pd.to_datetime(pm_all["ts_utc"], utc=True)
pm_all["market_id"] = pm_all["market_id"].astype(str)
pm_all = pm_all[pm_all["market_id"].isin(pm_ids_needed)].copy()
pm_all = pm_all.sort_values("ts_utc")
pm_all["usdc_amount"] = np.where(
    pm_all["maker_asset_id"].str.len() < 20,
    pm_all["maker_amount"],
    pm_all["taker_amount"]
).astype(float)
print(f"  {len(pm_all):,} PM trade rows for {pm_all['market_id'].nunique()} markets")

# -- Bar builder helpers ------------------------------------------------------
def make_bars(df, time_col, price_col, weight_col, freq, t0, t1):
    sub = df[(df[time_col] >= t0) & (df[time_col] <= t1)].copy()
    if sub.empty:
        return pd.DataFrame(columns=["last","vwap","n","vol"])
    sub["bar"] = sub[time_col].dt.floor(freq)
    sub["px_w"] = sub[price_col] * sub[weight_col]
    grp = sub.groupby("bar", sort=True).agg(
        n       = (price_col,  "count"),
        last    = (price_col,  "last"),
        sum_pxw = ("px_w",     "sum"),
        vol     = (weight_col, "sum"),
    )
    grp["vwap"] = grp["sum_pxw"] / grp["vol"].replace(0, np.nan)
    return grp[["last","vwap","n","vol"]]

def ffill_stale(s, limit):
    s_ff  = s.ffill(limit=limit)
    stale = s.isna() & s_ff.notna()
    return s_ff, stale

# -- Build panel per fight ----------------------------------------------------
panel_chunks = []
skipped = []

for _, fm in fmeta.iterrows():
    fid      = fm["fight_id"]
    tkr      = fm["yes_ticker"]
    pm_id    = fm["pm_id"]
    pm_flip  = fm["pm_flip"]
    fight_dt = pd.Timestamp(fm["event_date"]).tz_localize("UTC")
    t_start  = fight_dt - pd.Timedelta(hours=WIN_PRE)
    t_end    = fight_dt + pd.Timedelta(hours=WIN_POST)

    k_raw  = k_all[k_all["ticker"] == tkr]
    pm_raw = pm_all[pm_all["market_id"] == pm_id].copy()
    if pm_flip:
        pm_raw["price_yes"] = 1.0 - pm_raw["price_yes"]

    kb  = make_bars(k_raw,  "created_time", "price",    "count",       BAR_FREQ, t_start, t_end)
    pmb = make_bars(pm_raw, "ts_utc",       "price_yes","usdc_amount", BAR_FREQ, t_start, t_end)

    if kb.empty or pmb.empty:
        skipped.append({"fight_id": fid, "k_bars": len(kb), "pm_bars": len(pmb)})
        continue

    bar_idx = pd.date_range(t_start, t_end, freq=BAR_FREQ, tz="UTC", inclusive="left")
    kb  = kb.reindex(bar_idx)
    pmb = pmb.reindex(bar_idx)

    k_last_ff,  k_stale  = ffill_stale(kb["last"],  MAX_FFILL)
    pm_last_ff, pm_stale = ffill_stale(pmb["last"], MAX_FFILL)

    bars = pd.DataFrame({
        "fight_id": fid, "bar_utc": bar_idx,
        "k_last":   k_last_ff,  "k_vwap":  kb["vwap"],
        "k_n":      kb["n"].fillna(0).astype(int),
        "k_vol":    kb["vol"].fillna(0),
        "k_stale":  k_stale.fillna(False),
        "pm_last":  pm_last_ff, "pm_vwap": pmb["vwap"],
        "pm_n":     pmb["n"].fillna(0).astype(int),
        "pm_vol":   pmb["vol"].fillna(0),
        "pm_stale": pm_stale.fillna(False),
    })
    bars = bars[bars["k_last"].notna() | bars["pm_last"].notna()].copy()
    bars["both_traded"] = (bars["k_n"] > 0) & (bars["pm_n"] > 0)
    panel_chunks.append(bars)

panel = pd.concat(panel_chunks, ignore_index=True)
col_order = ["fight_id","bar_utc",
             "k_last","k_vwap","k_n","k_vol","k_stale",
             "pm_last","pm_vwap","pm_n","pm_vol","pm_stale",
             "both_traded"]
panel = panel[col_order]
panel.to_parquet(OUT_PANEL, index=False)
print(f"  saved {OUT_PANEL}  ({len(panel):,} rows)")

# -- Print coverage table -----------------------------------------------------
print()
print("=" * 100)
print("PHASE 2 PANEL — UPDATED COVERAGE TABLE")
print("=" * 100)
hdr = (f"  {'fight_id':<22} {'date':<12} {'fighters':<36}"
       f"  {'k_bars':>6} {'pm_bars':>7} {'both_bars':>10} {'both%':>6}"
       f"  {'k_n':>8} {'pm_n':>9}")
print(hdr)
print("  " + "-" * (len(hdr) - 2))

total_both = total_bars_all = 0
for _, fm in fmeta.iterrows():
    fid = fm["fight_id"]
    sub = panel[panel["fight_id"] == fid]
    k_names = ", ".join(fm["fighters_k"])[:34]
    date_s  = str(fm["event_date"].date())
    if sub.empty:
        print(f"  {fid:<22} {date_s:<12} [{k_names:<34}]  -- SKIPPED --")
        continue
    k_bars    = int((sub["k_n"] > 0).sum())
    pm_bars   = int((sub["pm_n"] > 0).sum())
    both_bars = int(sub["both_traded"].sum())
    n_bars    = len(sub)
    both_pct  = both_bars / n_bars * 100 if n_bars else 0
    k_n_tot   = int(sub["k_n"].sum())
    pm_n_tot  = int(sub["pm_n"].sum())
    print(f"  {fid:<22} {date_s:<12} [{k_names:<34}]"
          f"  {k_bars:>6} {pm_bars:>7} {both_bars:>10} {both_pct:>5.1f}%"
          f"  {k_n_tot:>8,} {pm_n_tot:>9,}")
    total_both     += both_bars
    total_bars_all += n_bars

print("=" * 100)
print(f"\n  Fights in panel:     {panel['fight_id'].nunique()}")
print(f"  Total bars:          {len(panel):,}")
both_overall = total_both / total_bars_all * 100 if total_bars_all else 0
print(f"  Both-traded (overall): {total_both:,} / {total_bars_all:,}  ({both_overall:.1f}%)")
print(f"\n  Rows appended to interim: {new_rows_added:,}")

if skipped:
    print(f"\n  Still excluded (zero trades in 72-h window): {len(skipped)}")
    for s in skipped:
        print(f"    {s['fight_id']}  k_bars={s['k_bars']}  pm_bars={s['pm_bars']}")
