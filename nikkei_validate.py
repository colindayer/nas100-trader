"""
Nikkei futures sweep — proper validation: correlation to a SAME-PERIOD Nasdaq
reference (NQ futures, 2024-26), rolling 6-month windows, decay. Pillar #4 gate.
"""
import pandas as pd, numpy as np, yfinance as yf, warnings
warnings.filterwarnings("ignore")
SLIP = 0.0002

def build(tkr):
    d = yf.download(tkr, period="730d", interval="1h", progress=False)
    if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.droplevel(1)
    d = d[["Open","High","Low","Close"]].dropna(); d.index = pd.to_datetime(d.index, utc=True)
    d["Date"]=d.index.date; d["H"]=d.index.hour
    dc=d.groupby("Date")["Close"].last(); dc.index=pd.to_datetime(dc.index)
    e50=dc.ewm(span=50).mean(); e200=dc.ewm(span=200).mean()
    d["E50"]=d["Date"].map(dict(zip(e50.index.date,e50))); d["E200"]=d["Date"].map(dict(zip(e200.index.date,e200)))
    pc=d["Close"].shift(1); tr=pd.concat([d["High"]-d["Low"],(d["High"]-pc).abs(),(d["Low"]-pc).abs()],axis=1).max(axis=1)
    a=tr.rolling(14).mean(); d["HV"]=a>1.5*a.rolling(200).mean()
    d["Asian"]=(d["H"]>=0)&(d["H"]<8); ab=d[d["Asian"]]; d["AL"]=d["Date"].map(ab.groupby("Date")["Low"].min())
    d["InS"]=(d["H"]>=8)&(d["H"]<16)
    d["sig"]=((d["Low"]<d["AL"])&(d["Close"]>d["AL"])&d["InS"]&(d["Close"]>d["E50"])&(d["E50"]>d["E200"])&~d["HV"]&d["AL"].notna()).astype(int)
    return d

def daily_pnl(d, sl=0.02, rr=3.0, risk=0.006):
    cap=10_000; rows={}; it=False; e=s=t=sh=0.; dt=None; cur=None; ds=cap; lock=False
    for i in range(1,len(d)):
        day=d["Date"].iloc[i]; price=float(d["Close"].iloc[i]); g=int(d["sig"].iloc[i-1])
        if day!=cur: cur=day; ds=cap; lock=False
        if (cap-ds)/max(ds,1)<=-0.05 or (cap-10000)/10000<=-0.10: lock=True
        if lock: continue
        if it:
            if price<=s: p=sh*(s-e)-sh*(e+s)*SLIP; cap+=p; rows[day]=rows.get(day,0)+p; it=False
            elif price>=t: p=sh*(t-e)-sh*(e+t)*SLIP; cap+=p; rows[day]=rows.get(day,0)+p; it=False
        elif g and dt!=day:
            it=True; dt=day; e=price; s=price*(1-sl); t=price*(1+sl*rr); sh=(cap*risk)/(price*sl)
    return pd.Series(rows)

nk = daily_pnl(build("NIY=F")); nk.index = pd.to_datetime(nk.index)
nq = daily_pnl(build("NQ=F"));  nq.index = pd.to_datetime(nq.index)
print("="*60); print("NIKKEI SWEEP VALIDATION (vs same-period NQ, 2024-26)"); print("="*60)

# Correlation to Nasdaq (same period now)
idx = pd.bdate_range(min(nk.index.min(),nq.index.min()), max(nk.index.max(),nq.index.max()))
a=nk.reindex(idx).fillna(0); b=nq.reindex(idx).fillna(0)
corr = a.corr(b)
print(f"\n[1] Correlation to Nasdaq (NQ) sweep daily P&L: {corr:+.3f}")
print(f"    -> {'UNCORRELATED ✅ genuine diversifier' if abs(corr)<0.25 else 'correlated — adds less'}")

# Rolling 6-month windows
print(f"\n[2] Rolling 6-month windows (consistency):")
starts=pd.date_range(nk.index.min().normalize(), nk.index.max(), freq="3MS"); pos=0; tot=0
for s0 in starts:
    s1=s0+pd.DateOffset(months=6); w=nk[(nk.index>=s0)&(nk.index<s1)]
    if len(w)<3: continue
    r=w.sum()/10_000; tot+=1; pos+=(r>0)
    print(f"    {s0.date()}→{s1.date()}: {r:>+6.1%} ({len(w)} trade-days)")
print(f"    Positive: {pos}/{tot} ({100*pos/max(tot,1):.0f}%)")
tot_ret=nk.sum()/10_000; print(f"\n[3] Total: {tot_ret:+.1%} over ~2y. Verdict: {'candidate ✅' if corr<0.25 and pos/max(tot,1)>0.5 else 'weak/correlated — hold'}")
print("="*60)
