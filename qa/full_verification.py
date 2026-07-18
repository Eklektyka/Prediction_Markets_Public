import requests, json, time
import pandas as pd
import numpy as np

REPO = 'C:/Users/micha/OneDrive/Pulpit/Kalshi/Prediction_Markets_Public'
headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}

def fetch_all_trades(cond_id):
    all_trades = []
    offset = 0
    while True:
        url = 'https://data-api.polymarket.com/trades?market={}&limit=500&offset={}'.format(cond_id, offset)
        for attempt in range(3):
            try:
                r = requests.get(url, headers=headers, timeout=30)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(2)
        if not data:
            break
        all_trades.extend(data)
        if len(data) < 500:
            break
        offset += 500
        time.sleep(0.3)
    return all_trades

audit_markets = {
    '648861': {
        'name': 'Radtke-vs-Frunza',
        'cond_id': '0xa2f892ea2dee9b8b1e13ff3da9186338e55080955beb0f1ca8cbd8fc2f668874',
        'yes_token': '112186847609724386807224937244453064383100921004067228146196115794546878882314',
        'no_token':  '68605428518877495336054187450544314299253584641043482864395861340568018933847',
    },
    '639347': {
        'name': 'Wood-vs-Delgado',
        'cond_id': '0xdfc47e3eef4aea51aff436539515f20137d2de9669eb78ae8acb913abb69d184',
        'yes_token': '371211092044307663667431157282747055703279752247532642544961761430345640267',
        'no_token':  '78355143980307463546806326350808265841215943229665706267946734762635345103211',
    },
    '550473': {
        'name': 'Bleda-vs-Horth',
        'cond_id': '0x4591dac34b927b1d9d902a9016cda09693b77561ec130f180e1998375f5784b6',
        'yes_token': '37491580685669407988269280267600217691838616901175483496909254992677150364685',
        'no_token':  '65311316878166762357868408982315856261429683125615064825327921951402061003825',
    },
    '550463': {
        'name': 'Usman-vs-Buckley',
        'cond_id': '0x15dc794f04549059da87dbf109e94733998d1d813e7ece9b14fd2a25fea84d96',
        'yes_token': '36309324973549302594422668112324360181963351286456294226781226224274628832725',
        'no_token':  '52027164242349849009424956031133018969572291169720738546945218860966281946183',
    },
    '839660': {
        'name': 'Kape-vs-Royval',
        'cond_id': '0x3d53194247ee26486ad18daea79e57c607e6f58ea4d9654cb205a899f1565413',
        'yes_token': '47030372077728629015997299567494082007604134612158802750567774493042022671875',
        'no_token':  '10696232637731654504364599492596856546891498568498387330387302949237730618882',
    },
}

print("=== FETCHING API TRADES ===")
api_data = {}
for mid, m in audit_markets.items():
    print("  {}...".format(m['name']), end=' ', flush=True)
    trades = fetch_all_trades(m['cond_id'])
    api_data[mid] = pd.DataFrame(trades)
    print(len(trades))

print("\n=== LOADING LYCHEE ===")
df = pd.read_parquet('{}/data/interim/polymarket_ufc_trades.parquet'.format(REPO))
df['ts_utc'] = pd.to_datetime(df['ts_utc'], utc=True)
df2025 = df[df['ts_utc'].dt.year == 2025].copy()
df2025['market_id'] = df2025['market_id'].astype(str)
df2025['taker_asset_id'] = df2025['taker_asset_id'].astype(str)
df2025['maker_asset_id'] = df2025['maker_asset_id'].astype(str)
print("2025 rows: {:,}".format(len(df2025)))

print("\n=== STOP-GATE VERIFICATION ===")
print()
print("{:<22} {:>10} {:>10} {:>8} {:>7} {:>7} {:>9} {:>7}".format(
    'Market', 'Lychee_raw', 'Lychee_YES', 'API_YES', 'API_NO', 'Ratio', 'VWAP_MAD', 'Result'))
print("-" * 90)

all_pass = True
results = []

for mid, m in audit_markets.items():
    name = m['name']
    yes_tok = m['yes_token']
    no_tok  = m['no_token']

    lychee_sub = df2025[df2025['market_id'] == mid].copy()
    raw_count = len(lychee_sub)

    lychee_yes = lychee_sub[lychee_sub['taker_asset_id'] == yes_tok].copy()
    filt_count = len(lychee_yes)

    api_df_m = api_data[mid]
    api_yes = api_df_m[api_df_m['asset'] == yes_tok]
    api_no  = api_df_m[api_df_m['asset'] != yes_tok]
    api_yes_count = len(api_yes)
    api_no_count  = len(api_no)

    ratio = filt_count / api_yes_count if api_yes_count > 0 else 0.0
    ratio_pass = 0.98 <= ratio <= 1.02

    lychee_yes = lychee_yes.copy()
    lychee_yes['usdc_vol'] = np.where(
        lychee_yes['maker_asset_id'] == '0',
        lychee_yes['maker_amount'],
        lychee_yes['taker_amount']
    ).astype(float)
    lychee_yes = lychee_yes[lychee_yes['usdc_vol'] > 0].copy()

    lychee_yes['bar'] = lychee_yes['ts_utc'].dt.floor('5min')
    lychee_yes['pw'] = lychee_yes['price_yes'] * lychee_yes['usdc_vol']
    lychee_g = lychee_yes.groupby('bar').agg(sum_pw=('pw','sum'), sum_w=('usdc_vol','sum'))
    lychee_g['vwap'] = lychee_g['sum_pw'] / lychee_g['sum_w'].replace(0, np.nan)

    api_yes_c = api_yes.copy()
    api_yes_c['ts'] = pd.to_datetime(api_yes_c['timestamp'], unit='s', utc=True)
    api_yes_c['price'] = api_yes_c['price'].astype(float)
    api_yes_c['size'] = api_yes_c['size'].astype(float)
    api_yes_c['bar'] = api_yes_c['ts'].dt.floor('5min')
    api_yes_c['pw'] = api_yes_c['price'] * api_yes_c['size']
    api_g = api_yes_c.groupby('bar').agg(sum_pw=('pw','sum'), sum_w=('size','sum'))
    api_g['vwap'] = api_g['sum_pw'] / api_g['sum_w'].replace(0, np.nan)

    common_bars = lychee_g.index.intersection(api_g.index)
    if len(common_bars) == 0:
        mad = 9999.0
    else:
        mad = float((lychee_g.loc[common_bars, 'vwap'] - api_g.loc[common_bars, 'vwap']).abs().mean())

    mad_pass = mad < 0.01
    pass_str = "PASS" if (ratio_pass and mad_pass) else "FAIL"
    if not (ratio_pass and mad_pass):
        all_pass = False

    print("{:<22} {:>10} {:>10} {:>8} {:>7} {:>7.4f} {:>9.5f} {:>7}".format(
        name, raw_count, filt_count, api_yes_count, api_no_count, ratio, mad, pass_str))
    results.append({
        'market': name, 'mid': mid, 'raw': raw_count, 'filtered': filt_count,
        'api_yes': api_yes_count, 'api_no': api_no_count, 'ratio': ratio, 'mad': mad,
        'pass': pass_str, 'ratio_ok': 0.98 <= ratio <= 1.02, 'mad_ok': mad < 0.01
    })

print()
if all_pass:
    print(">>> ALL 5 MARKETS PASS STOP-GATE <<<")
else:
    print(">>> STOP-GATE: SOME MARKETS FAIL <<<")
    for r_item in results:
        if r_item['pass'] == 'FAIL':
            print("  FAIL {}: ratio_ok={} (ratio={:.4f}), mad_ok={} (mad={:.5f})".format(
                r_item['market'], r_item['ratio_ok'], r_item['ratio'],
                r_item['mad_ok'], r_item['mad']))

# Save results for the report
import json as json2
with open('{}/qa/_stopgate_results.json'.format(REPO), 'w') as f:
    json2.dump({'all_pass': all_pass, 'results': results}, f, indent=2)
print("\nResults saved to qa/_stopgate_results.json")
