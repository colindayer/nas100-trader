"""
cross_sectional_cot_v2.py — Properly-constructed commodity hedging-pressure factor.
Fixes vs v1: (#2) DISAGGREGATED Producer/Merchant positioning (true hedgers, not
lumped 'commercial' incl. swap dealers); (#3) monthly not weekly (signal-to-noise);
(#4) INVERSE-VOL weighted legs (tames the -60% DD); rank-based long top / short
bottom tercile. Remaining cap: ETF returns bleed carry (#1, needs paid futures).
"""
import urllib.request, urllib.parse, json, pandas as pd, numpy as np
import yfinance as yf, warnings; warnings.filterwarnings("ignore")
from datetime import date

COST = 0.0015
DIS = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
COMMS = {  # name: (CFTC code, ETF)
    "oil":("067651","USO"), "natgas":("023651","UNG"), "gold":("088691","GLD"),
    "silver":("084691","SLV"), "copper":("085692","CPER"), "corn":("002602","CORN"),
    "soy":("005602","SOYB"), "wheat":("001602","WEAT"), "sugar":("080732","CANE"),
    "coffee":("083731","JO"), "cotton":("033661","BAL"),
}


def fetch_pm(code):
    rows = []; off = 0
    while True:
        q = {"$limit":"10000","$offset":str(off),"$where":f"cftc_contract_market_code='{code}'",
             "$select":"report_date_as_yyyy_mm_dd,prod_merc_positions_long,prod_merc_positions_short,open_interest_all"}
        d = json.loads(urllib.request.urlopen(urllib.request.Request(DIS+"?"+urllib.parse.urlencode(q), headers={"User-Agent":"r"}), timeout=60).read())
        if not d: break
        rows += d; off += len(d)
        if len(d) < 10000: break
    df = pd.DataFrame(rows)
    if df.empty: return None
    df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"])
    for c in ["prod_merc_positions_long","prod_merc_positions_short","open_interest_all"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("date").drop_duplicates("date")
    net = (df["prod_merc_positions_long"] - df["prod_merc_positions_short"]) / df["open_interest_all"]
    idx = net.rolling(156, min_periods=78).apply(lambda x: (x.iloc[-1] > x).mean())
    return pd.Series(idx.values, index=df["date"])


cot, ret = {}, {}
for name,(code,etf) in COMMS.items():
    s = fetch_pm(code)
    if s is None: print(f"  no COT {name}"); continue
    px = yf.download(etf, start="2006-01-01", end=str(date.today()), progress=False, auto_adjust=True)["Close"]
    if isinstance(px, pd.DataFrame): px = px.iloc[:,0]
    cot[name] = s.resample("ME").last()
    ret[name] = px.resample("ME").last().pct_change()
COT = pd.DataFrame(cot); RET = pd.DataFrame(ret)
idx = RET.index; COTm = COT.reindex(idx, method="ffill")
VOL = RET.rolling(6).std()
print(f"Universe ({len(RET.columns)}): {list(RET.columns)} | months: {len(idx)}")

rows = []
for i in range(7, len(idx)-1):
    sig = COTm.iloc[i].dropna()
    fwd = RET.iloc[i+1]; vol = VOL.iloc[i]
    sig = sig[[c for c in sig.index if pd.notna(fwd.get(c)) and pd.notna(vol.get(c)) and vol.get(c) > 0]]
    if len(sig) < 6: rows.append((idx[i+1], 0.0)); continue
    k = max(1, int(round(len(sig) * 0.35)))
    longs = sig.sort_values(ascending=False).index[:k]
    shorts = sig.sort_values().index[:k]
    def wret(names):
        w = (1/vol[names]); w = w/w.sum()
        return float((w * fwd[names]).sum())
    rows.append((idx[i+1], wret(longs) - wret(shorts) - 2*COST))
strat = pd.Series(dict(rows)).dropna()

qqq = yf.download("QQQ", start="2006-01-01", end=str(date.today()), progress=False, auto_adjust=True)["Close"]
if isinstance(qqq, pd.DataFrame): qqq = qqq.iloc[:,0]
qqqret = qqq.resample("ME").last().pct_change()

def block(lo, hi):
    s = strat[(strat.index.year>=lo)&(strat.index.year<=hi)]; s=s[s!=0]
    if len(s)<6: return None
    eq=(1+s).cumprod(); yrs=(s.index[-1]-s.index[0]).days/365.25
    return dict(n=len(s),wr=(s>0).mean(),cagr=eq.iloc[-1]**(1/yrs)-1 if yrs>0 else 0,
                sharpe=s.mean()/s.std()*np.sqrt(12) if s.std()>0 else 0,dd=(eq/eq.cummax()-1).min())

IS, OOS = block(2011,2018), block(2019,2026)
print("\n=== Cross-sectional COT v2 (Producer/Merchant, monthly, vol-weighted) ===")
for lab,m in [("IS  2011-18",IS),("OOS 2019-26",OOS)]:
    print(f"  {lab}: months={m['n']} win={m['wr']:.0%} CAGR={m['cagr']:+.1%} Sharpe={m['sharpe']:.2f} maxDD={m['dd']:.0%}")
corr = pd.DataFrame({"x":strat,"q":qqqret}).dropna().corr().iloc[0,1]
checks={"OOS Sharpe>0.5":OOS["sharpe"]>0.5,"maxDD>-35%":OOS["dd"]>-0.35,"OOS Sharpe<2.5":OOS["sharpe"]<2.5,
        "not overfit":OOS["sharpe"]<=IS["sharpe"]*1.3+0.5,">=30 months":OOS["n"]>=30,"IS Sharpe>0":IS["sharpe"]>0}
print("\n  GAUNTLET:")
for k,v in checks.items(): print(f"    [{'PASS' if v else 'FAIL'}] {k}")
print(f"    [{'PASS' if abs(corr)<0.3 else 'FAIL'}] low corr to QQQ: {corr:+.2f}")
print(f"\n  >>> {'PASSES — deployable diversifier' if all(checks.values()) and abs(corr)<0.3 else 'fails'}")
