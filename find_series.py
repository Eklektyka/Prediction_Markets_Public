#!/usr/bin/env python3
"""
find_series.py — discover Kalshi series tickers by keyword.

Your KXUFC guess returned nothing, which means UFC lives under a different series
ticker. This lists every series whose ticker/title/category/tags match your search
terms, so you can plug the real ticker into the collector.

Usage:
  python find_series.py                 # defaults to searching for UFC and MMA
  python find_series.py boxing tennis   # or any terms you like
"""
import os, sys, time, base64, requests
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

BASE = os.getenv("KALSHI_BASE_URL", "https://external-api.kalshi.com")
load_dotenv("env.env")
KEY_ID = os.getenv("KALSHI_KEYID")
PK = serialization.load_pem_private_key(open(os.getenv("KALSHI_KEYFILE"), "rb").read(), password=None)

def headers(method, path):
    ts = str(int(time.time() * 1000))
    sig = PK.sign((ts + method + path.split("?")[0]).encode(),
                  padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                  hashes.SHA256())
    return {"KALSHI-ACCESS-KEY": KEY_ID, "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode()}

def get(path, **params):
    params = {k: v for k, v in params.items() if v is not None}
    r = requests.get(BASE + path, headers=headers("GET", path), params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def all_series():
    """Page through every series."""
    out, cursor = [], None
    while True:
        page = get("/trade-api/v2/series", limit=1000, cursor=cursor)
        out.extend(page.get("series", []))
        cursor = page.get("cursor")
        if not cursor:
            break
        time.sleep(0.1)
    return out

def main():
    terms = [t.lower() for t in (sys.argv[1:] or ["ufc", "mma"])]
    print(f"searching series for: {', '.join(terms)}\n")
    try:
        series = all_series()
    except Exception as e:
        print(f"/series listing failed ({e}).")
        print("Fallback: open https://kalshi.com/sports/ufc, click a fight, and read the")
        print("ticker under 'Timeline & payout' — the series prefix is the part before the dates.")
        return
    print(f"scanned {len(series)} series total\n")
    hits = []
    for s in series:
        blob = " ".join(str(s.get(k, "")) for k in ("ticker", "title", "category", "tags")).lower()
        if any(t in blob for t in terms):
            hits.append(s)
    if not hits:
        print("No matches. Try other terms, or read a ticker off the website (see above).")
        return
    print(f"{'TICKER':<24} {'CATEGORY':<14} TITLE")
    print("-" * 80)
    for s in sorted(hits, key=lambda x: x.get("ticker", "")):
        print(f"{s.get('ticker',''):<24} {str(s.get('category','')):<14} {s.get('title','')}")
    print(f"\n{len(hits)} matching series. Put the UFC one(s) into SERIES and re-run the backfill.")

if __name__ == "__main__":
    main()
