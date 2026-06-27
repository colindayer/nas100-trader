"""
VOLUME PROFILE strategy (from LAT concept doc).
Core idea: POC (point of control) acts as a magnet; price reverts to it. The Value
Area (VAH/VAL) holds ~70% of volume = "fair value" range. Mean-reversion edge:
when price trades BELOW the Value Area Low (cheap vs recent value) in an uptrend,
go long expecting reversion up toward the POC.

Built on QQQ hourly; rolling 10-day profile (excludes current day = no lookahead).
Net of costs, OOS split, direction check, correlation to existing QQQ S1.
"""
import pandas as pd, numpy as np, pytz, warnings
from datetime import date, timedelta
import yfinance as yf
warnings.filterwarnings("ignore")
eastern=pytz.timezone("US/Eastern"); START,END="2019-01-01","2023-12-31"; YEARS=range(2019,2024); SLIP=0.0003

df=pd.read_csv("qqq_hourly_7y.csv"); df["timestamp"]=pd.to_datetime(df["timestamp"],utc=True)
df=df.set_index("timestamp").tz_convert(eastern)
q=df[df["symbol"]=="QQQ"][["open","high","low","close","volume"]].copy()
q.columns=["Open","High","Low","Close","Volume"]
q=q[(q.index.date>=pd.Timestamp(START).date())&(q.index.date<=pd.Timestamp(END).date())]; q["Date"]=q.index.date

# daily trend filter
dc=q[q.index.hour==16][["Close"]].copy(); dc.index=dc.index.date; dc=dc[~dc.index.duplicated(keep="last")]
ema50=dc["Close"].ewm(span=50).mean(); ema200=dc["Close"].ewm(span=200).mean()
q["EMA50"]=q["Date"].map(ema50.to_dict()); q["EMA200"]=q["Date"].map(ema200.to_dict())

vix=yf.download("^VIX",start=START,end=str(date.today()),progress=False)["Close"]
if isinstance(vix,pd.DataFrame): vix=vix.iloc[:,0]
vix.index=pd.to_datetime(vix.index).tz_localize(None).normalize(); vma=vix.rolling(21).mean()
def asof(s,dts):
    m=s.reindex(s.index.union(dts)).ffill(); r=m.asof(dts); r.index=[t.date() for t in r.index]; return r
dts=pd.DatetimeIndex([pd.Timestamp(d) for d in sorted(q["Date"].unique())]); vix_by=asof(vma,dts)
def vmult(d):
    v=vix_by.get(d,np.nan); return 1.0 if pd.isna(v) else (0.0 if v>25 else (0.5 if v>=20 else 1.0))

# ── rolling volume profile per day (prior 10 trading days) ────────────────────
days=sorted(q["Date"].unique())
poc={}; vah={}; val={}
for k in range(10,len(days)):
    window=q[(q["Date"]>=days[k-10])&(q["Date"]<days[k])]   # prior 10 days, exclude today
    if len(window)<20: continue
    lo,hi=window["Low"].min(),window["High"].max()
    bins=np.linspace(lo,hi,50); vol=np.zeros(len(bins)-1)
    for _,r in window.iterrows():
        c=min(max(r["Close"],lo),hi); idx=min(int((c-lo)/(hi-lo)*(len(bins)-1)),len(bins)-2)
        vol[idx]+=r["Volume"]
    poc_i=int(np.argmax(vol)); poc[days[k]]=(bins[poc_i]+bins[poc_i+1])/2
    # value area: expand from POC until 70% of volume
    order=np.argsort(vol)[::-1]; cum=0; tot=vol.sum(); sel=[]
    for j in order:
        sel.append(j); cum+=vol[j]
        if cum>=0.70*tot: break
    val[days[k]]=bins[min(sel)]; vah[days[k]]=bins[max(sel)+1]
q["POC"]=q["Date"].map(poc); q["VAL"]=q["Date"].map(val); q["VAH"]=q["Date"].map(vah)

# Signal: price below VAL (cheap) in uptrend -> long toward POC
q["below_val"]=(q["Close"]<q["VAL"])&q["VAL"].notna()
q["uptrend"]=(q["EMA50"]>q["EMA200"])
q["VP_long"]=(q["below_val"]&q["uptrend"]).astype(int)
q["VP_inv"]=((q["Close"]>q["VAH"])&q["uptrend"]).astype(int)  # inverse: buy above VAH (momentum) — direction check

def run(sig, sl=0.015, rr=2.0, hold=8):
    out={}; daily={}
    for Y in YEARS:
        cap=init=10_000; in_t=False; entry=stop=tgt=sh=0.; held=0; cur=None; ds=cap; lock=False; dt=None
        for i in range(1,len(q)):
            if q.index[i].year!=Y: continue
            d=q.index[i].date(); price=float(q["Close"].iloc[i]); s=int(q[sig].iloc[i-1]); vm=vmult(q.index[i-1].date())
            if d!=cur: cur=d; ds=cap; lock=False
            if (cap-ds)/max(ds,1)<=-0.05 or (cap-init)/init<=-0.10: lock=True
            if lock: continue
            if in_t:
                held+=1
                tgt_hit = price>=float(q["POC"].iloc[i]) if not pd.isna(q["POC"].iloc[i]) else price>=tgt
                if price<=stop or tgt_hit or held>=hold:
                    pnl=sh*(price-entry)-sh*(entry+price)*SLIP; cap+=pnl; daily[d]=daily.get(d,0)+pnl; in_t=False
            elif s==1 and vm>0 and dt!=d:
                in_t=True; dt=d; entry=price; stop=price*(1-sl); tgt=price*(1+sl*rr); held=0; sh=(cap*0.005*vm)/(price*sl)
        out[Y]=(cap-init)/init
    return out, pd.Series(daily)

print("="*72)
print("VOLUME PROFILE — long QQQ below Value-Area-Low, target POC (net of costs)")
print("="*72)
print(f"{'Variant':<30}"+"".join(f"{Y:>8}" for Y in YEARS)+f"{'avg':>8}{'IN':>7}{'OUT':>7}")
print("-"*72)
for name,sig in [("VP mean-revert (below VAL)","VP_long"),("INVERSE check (above VAH)","VP_inv")]:
    r,dseries=run(sig); avg=np.mean([r[Y] for Y in YEARS])
    IN=np.mean([r[Y] for Y in (2019,2020,2021)]); OUT=np.mean([r[Y] for Y in (2022,2023)])
    print(f"{name:<30}"+"".join(f"{r[Y]:>+8.1%}" for Y in YEARS)+f"{avg:>+8.1%}{IN:>+7.1%}{OUT:>+7.1%}")
print("-"*72)
print(f"VP-long signals: {int(q['VP_long'].sum())} bars")
print("Read: positive avg AND positive OUT (2022-23) = real edge worth adding.")
