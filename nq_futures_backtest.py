"""
NQ FUTURES test — our validated QQQ edge (Asian Sweep + ORB) on Nasdaq-100
futures. NQ tracks the SAME index as QQQ, so this is the true prop-firm port
(NQ/MNQ on a futures prop firm). If the edge is real, it ports here.

Data: yfinance NQ=F hourly (~2.4y, 2024-2026). Net of costs. Different period
than our 2019-2023 QQQ backtest = effectively an out-of-sample / new-regime test.
"""
import pandas as pd, numpy as np, warnings
import yfinance as yf
warnings.filterwarnings("ignore")
SLIP=0.0001

d=yf.download("NQ=F",period="730d",interval="1h",progress=False)
if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.droplevel(1)
d=d[["Open","High","Low","Close","Volume"]].copy()
d.index=pd.to_datetime(d.index)
if d.index.tz is None: d.index=d.index.tz_localize("UTC")
d.index=d.index.tz_convert("US/Eastern")
d["Date"]=d.index.date; d["H"]=d.index.hour

# trend (own EMAs on daily close)
dc=d[d["H"]==16][["Close"]].copy(); dc.index=dc.index.date; dc=dc[~dc.index.duplicated(keep="last")]
d["EMA50"]=d["Date"].map(dc["Close"].ewm(span=50).mean().to_dict())
d["EMA200"]=d["Date"].map(dc["Close"].ewm(span=200).mean().to_dict())
pc=d["Close"].shift(1); tr=pd.concat([d["High"]-d["Low"],(d["High"]-pc).abs(),(d["Low"]-pc).abs()],axis=1).max(axis=1)
atr=tr.rolling(14).mean(); d["HV"]=atr>1.5*atr.rolling(200).mean()

# Asian session low (18:00-02:00 ET), sweep + reclaim, RTH session entry
def isA(h): return h>=18 or h<2
d["A"]=d["H"].map(isA)
def sd(ts): return (ts+pd.Timedelta(days=1)).date() if ts.hour>=18 else ts.date()
d["SD"]=[sd(ts) for ts in d.index]
ab=d[d["A"]]; d["AL"]=d["SD"].map(ab.groupby("SD")["Low"].min())
d["InS"]=d["H"].map(lambda h:(2<=h<5) or (9<=h<12))
d["SL"]=(d["Low"]<d["AL"])&(d["Close"]>d["AL"])
d["S1"]=(d["SL"]&d["InS"]&(d["Close"]>d["EMA50"])&(d["EMA50"]>d["EMA200"])&~d["HV"]&d["AL"].notna()).astype(int)

# ORB: opening range = 9:00 ET bar (RTH open), breakout window 10-13, long-only uptrend
orb=d[d["H"]==9]; ohi={dt:r["High"] for dt,r in zip(orb["Date"],orb.to_dict("records"))}
olo={dt:r["Low"] for dt,r in zip(orb["Date"],orb.to_dict("records"))}
d["OHi"]=d["Date"].map(ohi); d["OLo"]=d["Date"].map(olo)
d["owin"]=d["H"].map(lambda h:10<=h<=13)
d["S5L"]=(d["owin"]&(d["Close"]>d["OHi"])&(d["EMA50"]>d["EMA200"])&d["OHi"].notna()).astype(int)

def run(sig, sl=0.012, rr=2.5):
    yrs={}
    for Y in sorted(set(d.index.year)):
        cap=init=10_000; in_t=False; entry=stop=tgt=sh=0.; dt=None; cur=None; ds=cap; lock=False
        dd=d[d.index.year==Y]
        for i in range(1,len(dd)):
            day=dd["Date"].iloc[i]; price=float(dd["Close"].iloc[i]); s=int(dd[sig].iloc[i-1])
            if day!=cur: cur=day; ds=cap; lock=False
            if (cap-ds)/max(ds,1)<=-0.05 or (cap-init)/init<=-0.10: lock=True
            if lock: continue
            if in_t:
                if price<=stop: cap+=sh*(stop-entry)-sh*(entry+stop)*SLIP; in_t=False
                elif price>=tgt: cap+=sh*(tgt-entry)-sh*(entry+tgt)*SLIP; in_t=False
            elif s==1 and dt!=day:
                in_t=True; dt=day; entry=price; stop=price*(1-sl); tgt=price*(1+sl*rr); sh=(cap*0.006)/(price*sl)
        yrs[Y]=(cap-init)/init
    return yrs

print("="*58)
print("NQ FUTURES — QQQ edge on Nasdaq-100 futures (net of costs)")
print("="*58)
yrs=sorted(set(d.index.year))
print(f"{'Strategy':<16}"+"".join(f"{y:>9}" for y in yrs)+f"{'avg':>9}")
print("-"*58)
for name,sig in [("S1 Asian Sweep","S1"),("S5 ORB Long","S5L")]:
    r=run(sig); avg=np.mean(list(r.values()))
    print(f"{name:<16}"+"".join(f"{r.get(y,0):>+9.1%}" for y in yrs)+f"{avg:>+9.1%}")
print("-"*58)
print(f"S1 signals: {int(d['S1'].sum())} | S5L signals: {int(d['S5L'].sum())}")
print("Data 2024-2026 (new regime vs our 2019-23 QQQ test). Positive = edge ports.")
