"""
cross_sectional_cot.py — Cross-sectional commodity hedging-pressure (COT) factor.
Documented to work better than single-commodity. Each week: rank ~10 commodities
by commercial-hedger positioning (3yr percentile). LONG the extreme-long names,
SHORT the extreme-short names, equal weight, market-neutral. Clean ETF returns,
costs, IS/OOS, correlation to equity book.
"""
import urllib.request, urllib.parse, json, pandas as pd, numpy as np
import yfinance as yf, warnings; warnings.filterwarnings("ignore")
from datetime import date

COST = 0.0015
BASE = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
# commodity: (CFTC contract code, tradeable ETF)
COMMS = {
    "oil":(  "067651","USO"), "natgas":("023651","UNG"), "gold":(  "088691","GLD"),
    "silver":("084691","SLV"), "copper":("085692","CPER"),"corn":(  "002602","CORN"),
    "soy":(  "005602","SOYB"), "wheat":( "001602","WEAT"), "sugar":( "080732","CANE"),
    "coffee":("083731","JO"),
}


def fetch_cot(code):
    rows = []; off = 0
    while True:
        q = {"$limit":"10000","$offset":str(off),"$where":f"cftc_contract_market_code='{code}'",
             "$select":"report_date_as_yyyy_mm_dd,comm_positions_long_all,comm_positions_short_all,open_interest_all"}
        url = BASE + "?" + urllib.parse.urlencode(q)
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"r"}), timeout=60).read())
        if not d: break
        rows += d; off += len(d)
        if len(d) < 10000: break
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"])
    for c in ["comm_positions_long_all","comm_positions_short_all","open_interest_all"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("date").drop_duplicates("date")
    net = (df["comm_positions_long_all"] - df["comm_positions_short_all"]) / df["open_interest_all"]
    idx = net.rolling(156, min_periods=52).apply(lambda x: (x.iloc[-1] > x).mean())
    return pd.Series(idx.values, index=df["date"])


# build weekly COT-index panel + ETF return panel
cot_idx = {}; etf_ret = {}
for name,(code,etf) in COMMS.items():
    try:
        cot_idx[name] = fetch_cot(code)
        px = yf.download(etf, start="2006-01-01", end=str(date.today()), progress=False, auto_adjust=True)["Close"]
        if isinstance(px, pd.DataFrame): px = px.iloc[:,0]
        etf_ret[name] = px.resample("W-FRI").last().pct_change()
    except Exception as e:
        print(f"  skip {name}: {type(e).__name__}")
COT = pd.DataFrame(cot_idx)
RET = pd.DataFrame(etf_ret)
idx = RET.index
COTw = COT.reindex(idx, method="ffill")
print(f"Universe: {list(RET.columns)}  | weeks: {len(idx)}")

# cross-sectional: long top-quintile COT, short bottom-quintile COT, equal weight, market-neutral
def strat_returns(hi=0.8, lo=0.2):
    out = []
    for i in range(1, len(idx)):
        sig = COTw.iloc[i-1].dropna()          # prior week's signal
        fwd = RET.iloc[i]
        longs = sig[sig > hi].index; shorts = sig[sig < lo].index
        longs = [c for c in longs if pd.notna(fwd.get(c))]
        shorts = [c for c in shorts if pd.notna(fwd.get(c))]
        if not longs and not shorts: out.append((idx[i], 0.0)); continue
        lr = fwd[longs].mean() if longs else 0.0
        sr = fwd[shorts].mean() if shorts else 0.0
        n = len(longs) + len(shorts)
        out.append((idx[i], lr - sr - COST * (n > 0)))   # crude turnover cost
    return pd.Series(dict(out))

strat = strat_returns().dropna()
qqq = yf.download("QQQ", start="2006-01-01", end=str(date.today()), progress=False, auto_adjust=True)["Close"]
if isinstance(qqq, pd.DataFrame): qqq = qqq.iloc[:,0]
qqqret = qqq.resample("W-FRI").last().pct_change()

def block(lo, hi):
    s = strat[(strat.index.year >= lo) & (strat.index.year <= hi)]
    s = s[s != 0]
    if len(s) < 5: return None
    eq = (1+s).cumprod(); yrs=(s.index[-1]-s.index[0]).days/365.25
    return dict(n=len(s), wr=(s>0).mean(), cagr=eq.iloc[-1]**(1/yrs)-1 if yrs>0 else 0,
                ret=eq.iloc[-1]-1, sharpe=s.mean()/s.std()*np.sqrt(52) if s.std()>0 else 0, dd=(eq/eq.cummax()-1).min())

IS, OOS = block(2010, 2017), block(2018, 2026)
print("\n=== Cross-sectional commodity COT (long extreme-long / short extreme-short) ===")
for lab, m in [("IS  2010-17", IS), ("OOS 2018-26", OOS)]:
    print(f"  {lab}: active_wks={m['n']} win={m['wr']:.0%} CAGR={m['cagr']:+.1%} "
          f"Sharpe={m['sharpe']:.2f} maxDD={m['dd']:.0%}")
corr = pd.DataFrame({"x":strat,"q":qqqret}).dropna().corr().iloc[0,1]
checks = {"OOS Sharpe>0.5":OOS["sharpe"]>0.5,"maxDD>-35%":OOS["dd"]>-0.35,"OOS Sharpe<2.5":OOS["sharpe"]<2.5,
          "not overfit":OOS["sharpe"]<=IS["sharpe"]*1.3+0.5,">=30 active wks":OOS["n"]>=30,"IS Sharpe>0":IS["sharpe"]>0}
print("\n  GAUNTLET:")
for k,v in checks.items(): print(f"    [{'PASS' if v else 'FAIL'}] {k}")
print(f"    [{'PASS' if abs(corr)<0.3 else 'FAIL'}] low corr to QQQ: {corr:+.2f}")
print(f"\n  >>> {'PASSES — real uncorrelated diversifier' if all(checks.values()) and abs(corr)<0.3 else 'fails'}")
