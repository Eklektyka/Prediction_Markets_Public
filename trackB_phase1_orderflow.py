#!/usr/bin/env python3
"""
trackB_phase1_orderflow.py — Track B, Phase 1 (FROZEN spec, commit 7d61b9c).

Tests, within KXUFCFIGHT markets, whether signed taker order-flow imbalance in one
5-minute interval predicts the price change into the next interval. Implements the
pre-registered specification exactly:
  - 5-minute event-time buckets within each fighter-market's active trading
  - OFI(t) = contracts(taker_side=yes) - contracts(taker_side=no)   [in interval t]
  - response = last_yes_price(t+1) - last_yes_price(t)              [non-overlapping]
  - regression of response on OFI(t) with fighter-market (ticker) fixed effects
  - inference: SE clustered by FIGHT, plus a within-market permutation test
    (with a single coefficient, Romano-Wolf collapses to this permutation test)
  - coverage floor: >=100 trades per market, and >=30 qualifying fights
  - holdout: the two most recent fight cards are SEALED and never touched here

No new dependencies (pandas + numpy only). Run from repo root:
  python trackB_phase1_orderflow.py

IMPORTANT: check the VALIDATION block it prints first. The fight_id derivation is the
one assumption I could not verify without your real tickers. If the derived fight count
is ~half the market count (two fighter-markets per bout), pairing worked. If it equals
the market count, the rule is wrong and the clustering/floor are off — paste the block
and we fix the one function.
"""
from __future__ import annotations
import glob, sys
from pathlib import Path
import numpy as np
import pandas as pd

RAW = "data/raw/live"
SERIES = "KXUFCFIGHT"
BUCKET = "5min"
MIN_TRADES_PER_MARKET = 100
MIN_FIGHTS = 30
N_HOLDOUT_CARDS = 2
N_PERM = 2000
RNG = np.random.default_rng(20260712)

# ---- fight / card identification (THE assumption to validate) -----------------
def fight_id(ticker: str) -> str:
    """Best structural guess: a bout's two fighter-markets share everything up to the
    final '-<outcome>' segment. e.g. KXUFCFIGHT-25JUL12ABC-FImar and -FIsil -> same bout."""
    return ticker.rsplit("-", 1)[0]

def load() -> pd.DataFrame:
    files = glob.glob(f"{RAW}/**/*.parquet", recursive=True)
    if not files:
        sys.exit(f"No parquet under {RAW}.")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df = df[df["ticker"].str.startswith(SERIES)].copy()
    if df.empty:
        sys.exit("No KXUFCFIGHT trades found.")
    df = df.drop_duplicates("trade_id")                          # raw is append-only
    df["created_time"] = pd.to_datetime(df["created_time"], utc=True, format="ISO8601")
    df["count"] = pd.to_numeric(df["count_fp"], errors="coerce")
    df["yes_price"] = pd.to_numeric(df["yes_price_dollars"], errors="coerce")
    df = df[df["taker_side"].isin(["yes", "no"])].dropna(subset=["count", "yes_price"])
    df["fight"] = df["ticker"].map(fight_id)
    df["card"] = df.groupby("ticker")["created_time"].transform("max").dt.date  # proxy: fight date
    return df.sort_values("created_time")

def bucketize(df: pd.DataFrame) -> pd.DataFrame:
    """Per (ticker, 5-min bucket): OFI and last yes-price; then next-interval price change."""
    df = df.copy()
    df["signed"] = np.where(df["taker_side"] == "yes", df["count"], -df["count"])
    df["bucket"] = df["created_time"].dt.floor(BUCKET)
    g = df.groupby(["fight", "ticker", "bucket"])
    b = g.agg(ofi=("signed", "sum"),
              last_price=("yes_price", "last"),
              n=("trade_id", "size")).reset_index().sort_values(["ticker", "bucket"])
    # response = price change INTO the next interval, per fighter-market
    b["price_next"] = b.groupby("ticker")["last_price"].shift(-1)
    b["dprice"] = b["price_next"] - b["last_price"]
    return b.dropna(subset=["dprice"])

def within(s: pd.Series, by: pd.Series) -> np.ndarray:
    """Fixed-effects demeaning within group `by`."""
    return (s - s.groupby(by).transform("mean")).to_numpy()

def fit(b: pd.DataFrame):
    """OLS of demeaned dprice on demeaned OFI (ticker FE), SE clustered by fight."""
    yq = within(b["dprice"], b["ticker"])
    xq = within(b["ofi"], b["ticker"])
    beta = float((xq @ yq) / (xq @ xq))
    u = yq - beta * xq
    sxx = xq @ xq
    # cluster-robust meat by fight
    meat = 0.0
    for _, idx in b.groupby("fight").indices.items():
        xg, ug = xq[idx], u[idx]
        s = float(xg @ ug); meat += s * s
    G = b["fight"].nunique()
    se = np.sqrt(meat) / sxx
    se *= np.sqrt(G / (G - 1)) if G > 1 else 1.0            # small-sample cluster correction
    t = beta / se
    return beta, se, t, G

def permutation_p(b: pd.DataFrame, beta_obs: float) -> float:
    """Permute OFI within each fighter-market, breaking the time link; two-sided p."""
    yq = within(b["dprice"], b["ticker"])
    xcol = b["ofi"].to_numpy().copy()
    tick = b["ticker"].to_numpy()
    order = {t: np.where(tick == t)[0] for t in np.unique(tick)}
    hits = 0
    for _ in range(N_PERM):
        xp = xcol.copy()
        for t, idx in order.items():
            xp[idx] = RNG.permutation(xcol[idx])
        xq = within(pd.Series(xp, index=b.index), b["ticker"])
        bperm = (xq @ yq) / (xq @ xq)
        if abs(bperm) >= abs(beta_obs):
            hits += 1
    return (hits + 1) / (N_PERM + 1)

def main():
    df = load()

    # ---- VALIDATION (check before trusting anything below) --------------------
    n_markets = df["ticker"].nunique(); n_fights = df["fight"].nunique()
    print("=" * 68); print("VALIDATION — confirm the fight grouping is right")
    print("=" * 68)
    print(f"fighter-markets: {n_markets}   derived fights: {n_fights}   "
          f"(expect fights ~= markets/2 if pairing worked)")
    print("\nsample tickers -> derived fight_id:")
    for t in sorted(df["ticker"].unique())[:12]:
        print(f"  {t:<34} -> {fight_id(t)}")
    print(f"\ndistinct fight cards (by fight date): {df['card'].nunique()}")
    print("=" * 68 + "\n")

    # ---- SEAL HOLDOUT: two most recent cards ----------------------------------
    cards = sorted(df["card"].unique())
    holdout_cards = set(cards[-N_HOLDOUT_CARDS:])
    hold = df[df["card"].isin(holdout_cards)]
    train = df[~df["card"].isin(holdout_cards)]
    Path("data/holdout").mkdir(parents=True, exist_ok=True)
    (Path("data/holdout") / "trackB_phase1_holdout_fights.txt").write_text(
        "\n".join(sorted(hold["fight"].unique())))
    print(f"HOLDOUT sealed: cards {sorted(map(str,holdout_cards))} "
          f"({hold['fight'].nunique()} fights) — NOT used below.\n")

    # ---- coverage floor on TRAINING -------------------------------------------
    tc = train.groupby("ticker")["trade_id"].size()
    keep = tc[tc >= MIN_TRADES_PER_MARKET].index
    train = train[train["ticker"].isin(keep)]
    q_fights = train["fight"].nunique()
    print(f"coverage floor: {len(keep)} markets with >={MIN_TRADES_PER_MARKET} trades; "
          f"{q_fights} qualifying fights (need >={MIN_FIGHTS}).")
    if q_fights < MIN_FIGHTS:
        print("\nRESULT: COVERAGE-LIMITED — floor not met. Reported as such per the plan; "
              "no significance claim.")
        return

    # ---- build panel and fit --------------------------------------------------
    b = bucketize(train)
    print(f"panel: {len(b):,} bucket-observations across {b['ticker'].nunique()} markets, "
          f"{b['fight'].nunique()} fights.\n")
    beta, se, t, G = fit(b)
    p_perm = permutation_p(b, beta)

    print("-" * 68); print("TRACK B PHASE 1 — order-flow predictive regression")
    print("-" * 68)
    print(f"  OFI coefficient (beta) : {beta:+.6e}   [yes-price move per net contract]")
    print(f"  cluster SE (by fight)  : {se:.6e}   (G = {G} clusters)")
    print(f"  t-statistic            : {t:+.3f}")
    print(f"  permutation p (2-sided): {p_perm:.4f}   ({N_PERM} perms)")
    ci_lo, ci_hi = beta - 1.96 * se, beta + 1.96 * se
    print(f"  95% CI (cluster)       : [{ci_lo:+.3e}, {ci_hi:+.3e}]")

    print("\nKILL RULE (frozen): shelve if CI contains 0 at p>0.05 after permutation.")
    verdict = ("SHELVE order-flow signal (not distinguishable from zero)"
               if (ci_lo <= 0 <= ci_hi) or p_perm > 0.05
               else "SIGNAL SURVIVES pre-registered test — proceed to holdout scoring")
    print(f"VERDICT: {verdict}")

    Path("qa").mkdir(exist_ok=True)
    (Path("qa") / "trackB_phase1_results.txt").write_text(
        f"beta={beta:.6e}\nse={se:.6e}\nt={t:.4f}\nperm_p={p_perm:.4f}\n"
        f"CI=[{ci_lo:.4e},{ci_hi:.4e}]\nG={G}\nqualifying_fights={q_fights}\n"
        f"verdict={verdict}\n")
    print("\nsaved -> qa/trackB_phase1_results.txt")

if __name__ == "__main__":
    main()
