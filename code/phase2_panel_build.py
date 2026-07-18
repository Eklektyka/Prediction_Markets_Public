"""
phase2_panel_build.py — Build 5-min prototype panel for top-20 UFC fights

Inputs:
  data/meta/ufc_crosswalk.parquet          — fight metadata + venue IDs
  lychee/kalshi/trades/*.parquet           — Kalshi YES-ticker trades
  data/interim/polymarket_ufc_trades.parquet — PM CLOB trades

Outputs:
  data/clean/phase2_prototype_panel.parquet      — pre-window bars (72 h)
  data/interim/phase2_postwindow_bars.parquet    — bars after t_end (in-play)

Per-bar columns (5-min, UTC-aligned):
  fight_id, bar_utc
  k_last, k_vwap, k_n, k_vol, k_stale    (Kalshi YES ticker; vol = contracts)
  pm_last, pm_vwap, pm_n, pm_vol, pm_stale  (same outcome; vol = n trades)
  both_traded                              (k_n > 0 AND pm_n > 0 in this bar)

Staleness: last price forward-filled <= 60 min; k_stale/pm_stale=True when filled.
Window: t_end = Kalshi close_time - 60 min (per fight); t_start = t_end - 72 h.
  Same t_end applied to both venues. Bars after t_end tagged separately.
Excluded: fights where either venue has zero trades in the 72-h window.
"""

import json, re, sys, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── paths ─────────────────────────────────────────────────────────────────────
REPO   = Path(r"C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public")
LYCHEE = Path(r"C:\Kalshi_data\lychee\extracted\data")

OUT_CROSSWALK = REPO / "data" / "meta"    / "ufc_crosswalk.parquet"
PM_TRADES     = REPO / "data" / "interim" / "polymarket_ufc_trades.parquet"
OUT_PANEL     = REPO / "data" / "clean"   / "phase2_prototype_panel.parquet"
OUT_POSTWIN   = REPO / "data" / "interim" / "phase2_postwindow_bars.parquet"
OUT_PANEL.parent.mkdir(parents=True, exist_ok=True)
OUT_POSTWIN.parent.mkdir(parents=True, exist_ok=True)

K_MARKETS_DIR = LYCHEE / "kalshi" / "markets"
K_TRADES_DIR  = LYCHEE / "kalshi" / "trades"

BAR_FREQ  = "5min"
MAX_FFILL = 12        # 12 × 5 min = 60 min max staleness
WIN_PRE   = 72        # hours; t_start = t_end - WIN_PRE
WIN_POST_CLOSE = 2    # hours of post-window bars to capture after t_end

# ── helpers ───────────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\s]", "", s.lower()).strip()

def name_overlap(a: str, b: str) -> int:
    return len(set(norm(a).split()) & set(norm(b).split()))

# ── 1. Load crosswalk, select top-20 exact by combined volume ─────────────────
print("[1] loading crosswalk...")
cw = pd.read_parquet(OUT_CROSSWALK)
for col in ["fighters_kalshi", "tickers", "fighters_pm", "outcomes", "clob_token_ids"]:
    cw[col] = cw[col].apply(
        lambda x: json.loads(x) if isinstance(x, str) and x else
                  (x if isinstance(x, list) else [])
    )

exact = cw[cw["match_confidence"] == "exact"].copy()
exact["combined_vol"] = exact["kalshi_volume"].fillna(0) + exact["pm_volume"].fillna(0)
top20 = exact.nlargest(20, "combined_vol").reset_index(drop=True)

print(f"  {len(exact)} exact-matched fights  |  selecting top-20 by combined volume")
for i, r in top20.iterrows():
    k_names = ", ".join(r["fighters_kalshi"])
    print(f"  #{i+1:2d}  {r['event_date'].date()}  [{k_names}]"
          f"  combined_vol={r['combined_vol']:>14,.0f}  slug={r['pm_slug']}")

# ── 2. Build ticker→name and ticker→close_time from Kalshi markets ───────────
print("\n[2] building ticker->name and ticker->close_time maps...")
ticker_to_name:  dict[str, str]             = {}
ticker_to_close: dict[str, pd.Timestamp]   = {}
for f in sorted(K_MARKETS_DIR.glob("*.parquet")):
    df = pd.read_parquet(f, columns=["ticker", "title", "close_time"])
    ufc = df[df["ticker"].str.startswith("KXUFC", na=False)]
    for _, row in ufc.iterrows():
        tkr = row["ticker"]
        m = re.match(r"Will (.+?) win the .+ vs .+ professional MMA", row["title"])
        if m:
            ticker_to_name[tkr] = m.group(1).strip()
        ct = row.get("close_time")
        if ct is not None and pd.notna(ct):
            ts = pd.Timestamp(ct)
            ticker_to_close[tkr] = (ts.tz_localize("UTC") if ts.tzinfo is None
                                    else ts.tz_convert("UTC"))
print(f"  {len(ticker_to_name)} ticker->name  |  {len(ticker_to_close)} ticker->close_time")

# ── 3. Determine YES ticker + PM price direction per fight ────────────────────
print("\n[3] selecting YES tickers and side alignment...")
fight_meta = []
for _, fight in top20.iterrows():
    tickers    = fight["tickers"]
    fighters_p = fight["fighters_pm"] or []

    # PM YES fighter = fighters_pm[0] (PM outcomes[0])
    pm_yes_name = fighters_p[0] if fighters_p else ""

    # Find Kalshi ticker whose fighter best matches pm_yes_name
    best_tkr, best_score = (tickers[0] if tickers else ""), -1
    for t in tickers:
        sc = name_overlap(pm_yes_name, ticker_to_name.get(t, ""))
        if sc > best_score:
            best_score = sc
            best_tkr = t

    # pm_flip: True means PM price_yes must be inverted to align with yes_ticker
    pm_flip = (best_score == 0 and len(tickers) >= 2)
    k_yes_name = ticker_to_name.get(best_tkr, "?")

    if pm_flip:
        print(f"  WARNING: {fight['fight_id']} name_score=0, pm_flip=True  "
              f"pm_yes_name={pm_yes_name!r}  k_yes={k_yes_name!r}")

    # Per-fight window: t_end = Kalshi close_time − 60 min; t_start = t_end − 72 h
    close_ts = ticker_to_close.get(best_tkr)
    if close_ts is None:               # try the other ticker in the pair
        for t in tickers:
            if t != best_tkr and t in ticker_to_close:
                close_ts = ticker_to_close[t]
                break
    if close_ts is None:               # final fallback (should not happen)
        close_ts = (pd.Timestamp(fight["event_date"]).tz_localize("UTC")
                    + pd.Timedelta(hours=30))
        print(f"  WARNING: {fight['fight_id']} close_time not found; using fallback")
    # Floor to 5-min boundary so bar_idx aligns with dt.floor("5min") keys
    t_end   = (close_ts - pd.Timedelta(minutes=60)).floor("5min")
    t_start = t_end - pd.Timedelta(hours=WIN_PRE)   # 72 h = 4320 min; stays 5-min aligned

    fight_meta.append({
        "fight_id":    fight["fight_id"],
        "event_date":  fight["event_date"],
        "pm_id":       str(fight["pm_id"]),
        "yes_ticker":  best_tkr,
        "k_yes_name":  k_yes_name,
        "pm_flip":     pm_flip,
        "combined_vol": fight["combined_vol"],
        "fighters_k":  fight["fighters_kalshi"],
        "fighters_p":  fight["fighters_pm"],
        "t_start":     t_start,
        "t_end":       t_end,
        "close_time":  close_ts,
    })

fmeta = pd.DataFrame(fight_meta)
print(f"  YES tickers selected (all name_score >= 1 unless warned above)")
print(f"  Per-fight windows (t_start / t_end = close_time - 60 min):")
for _, fm in fmeta.iterrows():
    print(f"    {fm['fight_id']:<22}  {str(fm['t_start'])[:19]}  ->  "
          f"{str(fm['t_end'])[:19]}  (close={str(fm['close_time'])[:19]})")

# ── 4. Scan Kalshi trades for all YES tickers (single pass) ──────────────────
yes_tickers = set(fmeta["yes_ticker"].dropna().tolist())
yes_arr = pa.array(list(yes_tickers), type=pa.string())
print(f"\n[4] scanning Kalshi trades for {len(yes_tickers)} YES tickers "
      f"across {len(list(K_TRADES_DIR.glob('*.parquet')))} files...")

k_chunks = []
for f in sorted(K_TRADES_DIR.glob("*.parquet")):
    try:
        tbl = pq.read_table(f, columns=["ticker", "yes_price", "count", "created_time"])
        hit = tbl.filter(pc.is_in(tbl.column("ticker"), value_set=yes_arr))
        if hit.num_rows > 0:
            k_chunks.append(hit.to_pandas())
    except Exception:
        continue

k_all = (pd.concat(k_chunks, ignore_index=True) if k_chunks
         else pd.DataFrame(columns=["ticker", "yes_price", "count", "created_time"]))
k_all["created_time"] = pd.to_datetime(k_all["created_time"], utc=True)
k_all["price"] = k_all["yes_price"] / 100.0
k_all["count"] = pd.to_numeric(k_all["count"], errors="coerce").fillna(1).astype(float)
k_all = k_all.sort_values("created_time")
print(f"  {len(k_all):,} Kalshi trade rows")

# ── 5. Load PM trades for the 20 market IDs ──────────────────────────────────
print(f"\n[5] loading PM trades...")
pm_ids_needed = set(fmeta["pm_id"].tolist())
pm_all = pd.read_parquet(PM_TRADES)
pm_all["ts_utc"] = pd.to_datetime(pm_all["ts_utc"], utc=True)
pm_all["market_id"] = pm_all["market_id"].astype(str)
pm_all = pm_all[pm_all["market_id"].isin(pm_ids_needed)].copy()
pm_all = pm_all.sort_values("ts_utc")
print(f"  {len(pm_all):,} PM trade rows for {pm_all['market_id'].nunique()} markets "
      f"(of {len(pm_ids_needed)} needed)")

# PM volume proxy: the USDC side of each trade.
# Heuristic: maker_asset_id length < 20 chars → USDC maker → usdc = maker_amount
#            else → outcome-token maker → USDC paid by taker → usdc = taker_amount
pm_all["usdc_amount"] = np.where(
    pm_all["maker_asset_id"].str.len() < 20,
    pm_all["maker_amount"],
    pm_all["taker_amount"]
).astype(float)

# ── 6. Build 5-min panel per fight ───────────────────────────────────────────
print("\n[6] building 5-min bars per fight...")

def make_bars(trades_df, time_col, price_col, weight_col, bar_freq, t_start, t_end):
    """
    Aggregate trades into fixed-width bars. Returns DataFrame indexed by bar time.
    weight_col is used for VWAP; n_col = row count.
    """
    df = trades_df[(trades_df[time_col] >= t_start) & (trades_df[time_col] <= t_end)].copy()

    if df.empty:
        return pd.DataFrame(columns=["last", "vwap", "n", "vol"])

    df["bar"] = df[time_col].dt.floor(bar_freq)
    df["px_w"] = df[price_col] * df[weight_col]

    grp = df.groupby("bar", sort=True).agg(
        n    = (price_col,  "count"),
        last = (price_col,  "last"),     # sorted by time_col → chronological last
        sum_pxw = ("px_w", "sum"),
        vol  = (weight_col, "sum"),
    )
    grp["vwap"] = grp["sum_pxw"] / grp["vol"].replace(0, np.nan)
    return grp[["last", "vwap", "n", "vol"]]

def apply_stale_ffill(s_raw, max_fill):
    """
    Forward-fill a price series up to max_fill bars.
    Returns (s_filled, stale_mask) where stale_mask=True on filled bars.
    """
    s_ff    = s_raw.ffill(limit=max_fill)
    stale   = s_raw.isna() & s_ff.notna()
    return s_ff, stale

panel_chunks  = []
postwin_chunks = []
skipped       = []

for _, fm in fmeta.iterrows():
    fid        = fm["fight_id"]
    tkr        = fm["yes_ticker"]
    pm_id      = fm["pm_id"]
    pm_flip    = fm["pm_flip"]
    t_start    = fm["t_start"]
    t_end      = fm["t_end"]
    close_time = fm["close_time"]
    t_postend  = close_time + pd.Timedelta(hours=WIN_POST_CLOSE)

    # Filter trade sets for this fight
    k_raw  = k_all[k_all["ticker"] == tkr]
    pm_raw = pm_all[pm_all["market_id"] == pm_id].copy()
    if pm_flip:
        pm_raw["price_yes"] = 1.0 - pm_raw["price_yes"]

    # -- Main-window bars [t_start, t_end) ------------------------------------
    kb  = make_bars(k_raw,  "created_time", "price",    "count",       BAR_FREQ, t_start, t_end)
    pmb = make_bars(pm_raw, "ts_utc",       "price_yes","usdc_amount", BAR_FREQ, t_start, t_end)

    if kb.empty or pmb.empty:
        skipped.append({"fight_id": fid, "k_bars": len(kb), "pm_bars": len(pmb)})
        print(f"  SKIP {fid}: k_bars={len(kb)}, pm_bars={len(pmb)}")
    else:
        bar_idx = pd.date_range(t_start, t_end, freq=BAR_FREQ, tz="UTC", inclusive="left")
        kb  = kb.reindex(bar_idx)
        pmb = pmb.reindex(bar_idx)

        k_last_ff,  k_stale  = apply_stale_ffill(kb["last"],  MAX_FFILL)
        pm_last_ff, pm_stale = apply_stale_ffill(pmb["last"], MAX_FFILL)

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

    # -- Post-window bars [t_end, close_time + WIN_POST_CLOSE h) --------------
    # These include the in-play and settlement period; saved separately.
    kb_pw  = make_bars(k_raw,  "created_time", "price",    "count",       BAR_FREQ, t_end, t_postend)
    pmb_pw = make_bars(pm_raw, "ts_utc",       "price_yes","usdc_amount", BAR_FREQ, t_end, t_postend)

    if not kb_pw.empty or not pmb_pw.empty:
        pw_idx = pd.date_range(t_end, t_postend, freq=BAR_FREQ, tz="UTC", inclusive="left")
        kb_pw  = kb_pw.reindex(pw_idx)
        pmb_pw = pmb_pw.reindex(pw_idx)

        pw_bars = pd.DataFrame({
            "fight_id": fid, "bar_utc": pw_idx,
            "k_last":   kb_pw["last"],  "k_vwap":  kb_pw["vwap"],
            "k_n":      kb_pw["n"].fillna(0).astype(int),
            "k_vol":    kb_pw["vol"].fillna(0),
            "pm_last":  pmb_pw["last"], "pm_vwap": pmb_pw["vwap"],
            "pm_n":     pmb_pw["n"].fillna(0).astype(int),
            "pm_vol":   pmb_pw["vol"].fillna(0),
        })
        pw_bars = pw_bars[pw_bars["k_n"] > 0 | (pw_bars["pm_n"] > 0)].copy()
        pw_bars["both_traded"] = (pw_bars["k_n"] > 0) & (pw_bars["pm_n"] > 0)
        if not pw_bars.empty:
            postwin_chunks.append(pw_bars)

# ── 7. Assemble and save ──────────────────────────────────────────────────────
if not panel_chunks:
    sys.exit("ERROR: no fights survived filtering — check trade file paths")

panel = pd.concat(panel_chunks, ignore_index=True)
col_order = [
    "fight_id", "bar_utc",
    "k_last", "k_vwap", "k_n", "k_vol", "k_stale",
    "pm_last", "pm_vwap", "pm_n", "pm_vol", "pm_stale",
    "both_traded",
]
panel = panel[col_order]
panel.to_parquet(OUT_PANEL, index=False)
print(f"\n[7] saved {OUT_PANEL}  ({len(panel):,} rows)")

# Post-window parquet
if postwin_chunks:
    postwin = pd.concat(postwin_chunks, ignore_index=True)
    pw_cols = ["fight_id","bar_utc",
               "k_last","k_vwap","k_n","k_vol",
               "pm_last","pm_vwap","pm_n","pm_vol","both_traded"]
    postwin = postwin[[c for c in pw_cols if c in postwin.columns]]
    postwin.to_parquet(OUT_POSTWIN, index=False)
    print(f"    post-window: {OUT_POSTWIN}  ({len(postwin):,} rows, "
          f"{postwin['fight_id'].nunique()} fights)")
else:
    print("    post-window: no bars captured")

# ── 8. Print summary table ────────────────────────────────────────────────────
print()
print("=" * 100)
print("PHASE 2 PROTOTYPE PANEL — FIGHT SUMMARY")
print("=" * 100)

hdr = (f"  {'fight_id':<22} {'date':<12} {'fighters':<36}"
       f"  {'k_bars':>6} {'pm_bars':>7} {'both_bars':>10}"
       f" {'both%':>6}  {'k_n':>8} {'pm_n':>9}")
print(hdr)
print("  " + "-" * (len(hdr) - 2))

total_both = 0
total_bars = 0

for _, fm in fmeta.iterrows():
    fid = fm["fight_id"]
    sub = panel[panel["fight_id"] == fid]
    if sub.empty:
        k_names = ", ".join(fm["fighters_k"])[:34]
        print(f"  {fid:<22} {str(fm['event_date'].date()):<12} [{k_names}]  -- SKIPPED --")
        continue

    k_bars    = int((sub["k_n"] > 0).sum())
    pm_bars   = int((sub["pm_n"] > 0).sum())
    both_bars = int(sub["both_traded"].sum())
    n_bars    = len(sub)
    both_pct  = both_bars / n_bars * 100 if n_bars else 0
    k_n_tot   = int(sub["k_n"].sum())
    pm_n_tot  = int(sub["pm_n"].sum())
    k_names   = ", ".join(fm["fighters_k"])[:34]
    date_str  = str(fm["event_date"].date())

    print(f"  {fid:<22} {date_str:<12} [{k_names:<34}]"
          f"  {k_bars:>6} {pm_bars:>7} {both_bars:>10}"
          f" {both_pct:>5.1f}%  {k_n_tot:>8,} {pm_n_tot:>9,}")

    total_both += both_bars
    total_bars += n_bars

print("=" * 100)
print(f"\n  Fights in panel:          {panel['fight_id'].nunique()}")
print(f"  Total bars:               {len(panel):,}")
print(f"  Overall BOTH-traded bars: {total_both:,} / {total_bars:,}"
      f"  ({total_both/total_bars*100:.1f}%)" if total_bars else "")
print(f"  Panel file:               {OUT_PANEL}")

if skipped:
    print(f"\n  Excluded (zero trades in 72-h window): {len(skipped)}")
    for s in skipped:
        print(f"    {s['fight_id']}  k_bars={s['k_bars']}  pm_bars={s['pm_bars']}")

# DVAOMA trade-capture diagnostic
dvaoma_fmeta = fmeta[fmeta["fight_id"] == "20250607_DVAOMA"]
if not dvaoma_fmeta.empty:
    fm_dv   = dvaoma_fmeta.iloc[0]
    tkr_dv  = fm_dv["yes_ticker"]
    # Both tickers for the fight (we need total, not just YES-ticker)
    dv_row  = top20[top20["fight_id"] == "20250607_DVAOMA"]
    all_tkrs = dv_row.iloc[0]["tickers"] if not dv_row.empty else [tkr_dv]
    all_arr  = pa.array(all_tkrs, type=pa.string())
    total_k  = 0
    in_win_k = 0
    for f in sorted(K_TRADES_DIR.glob("*.parquet")):
        try:
            tbl = pq.read_table(f, columns=["ticker","created_time"])
            hit = tbl.filter(pc.is_in(tbl.column("ticker"), value_set=all_arr))
            if hit.num_rows:
                df_h = hit.to_pandas()
                df_h["created_time"] = pd.to_datetime(df_h["created_time"], utc=True)
                total_k  += len(df_h)
                in_win_k += ((df_h["created_time"] >= fm_dv["t_start"]) &
                             (df_h["created_time"] <= fm_dv["t_end"])).sum()
        except Exception:
            continue
    dv_sub = panel[panel["fight_id"] == "20250607_DVAOMA"]
    print(f"\n  DVAOMA trade-capture (both Kalshi tickers, combined):")
    print(f"    Window: {str(fm_dv['t_start'])[:19]} -> {str(fm_dv['t_end'])[:19]}")
    print(f"    Total Kalshi trades (all time): {total_k:,}")
    print(f"    In-window Kalshi trades:        {in_win_k:,}  ({in_win_k/total_k*100:.1f}%)")
    print(f"    Panel k_n (YES ticker only):    {int(dv_sub['k_n'].sum()):,}")
