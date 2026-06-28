"""
Sweep on global index FUTURES (24h data — overnight session exists, unlike cash).
Tests whether the validated Asian-sweep transfers to Nikkei (diversifying, Japan)
and Russell (does 24h data rescue the failed IWM cash test?). Same logic as the
BTC/QQQ sweep, NO tuning. Net of costs. + correlation to QQQ sweep.
"""
import pandas as pd, numpy as np, yfinance as yf, warnings
warnings.filterwarnings("ignore")
SLIP = 0.0002

def build(tkr):
    d = yf.download(tkr, period="730d", interval="1h", progress=False)
    if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.droplevel(1)
    d = d[["Open","High","Low","Close"]].dropna()
    d.index = pd.to_datetime(d.index, utc=True)
    d["Date"] = d.index.date; d["H"] = d.index.hour
    dc = d.groupby("Date")["Close"].last(); dc.index = pd.to_datetime(dc.index)
    e50 = dc.ewm(span=50).mean(); e200 = dc.ewm(span=200).mean()
    d["E50"] = d["Date"].map(dict(zip(e50.index.date, e50)))
    d["E200"] = d["Date"].map(dict(zip(e200.index.date, e200)))
    pc = d["Close"].shift(1)
    tr = pd.concat([d["High"]-d["Low"],(d["High"]-pc).abs(),(d["Low"]-pc).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean(); d["HV"] = atr > 1.5*atr.rolling(200).mean()
    # Asian range 00-08 UTC, reclaim window 08-16 UTC (same as BTC/QQQ sweep)
    d["Asian"] = (d["H"] >= 0) & (d["H"] < 8)
    ab = d[d["Asian"]]; d["AL"] = d["Date"].map(ab.groupby("Date")["Low"].min())
    d["InS"] = (d["H"] >= 8) & (d["H"] < 16)
    d["sig"] = ((d["Low"]<d["AL"]) & (d["Close"]>d["AL"]) & d["InS"] &
                (d["Close"]>d["E50"]) & (d["E50"]>d["E200"]) & ~d["HV"] & d["AL"].notna()).astype(int)
    return d

def run(d, sl=0.02, rr=3.0, risk=0.006):
    yrs = {}; daily = {}
    for Y in sorted(set(d.index.year)):
        cap=init=10_000; it=False; e=s=t=sh=0.; dt=None; ds=cap; cur=None; lock=False
        dd = d[d.index.year == Y]
        for i in range(1, len(dd)):
            day=dd["Date"].iloc[i]; price=float(dd["Close"].iloc[i]); g=int(dd["sig"].iloc[i-1])
            if day!=cur: cur=day; ds=cap; lock=False
            if (cap-ds)/max(ds,1)<=-0.05 or (cap-init)/init<=-0.10: lock=True
            if lock: continue
            if it:
                if price<=s: p=sh*(s-e)-sh*(e+s)*SLIP; cap+=p; daily[day]=daily.get(day,0)+p; it=False
                elif price>=t: p=sh*(t-e)-sh*(e+t)*SLIP; cap+=p; daily[day]=daily.get(day,0)+p; it=False
            elif g and dt!=day:
                it=True; dt=day; e=price; s=price*(1-sl); t=price*(1+sl*rr); sh=(cap*risk)/(price*sl)
        yrs[Y]=(cap-init)/init
    return yrs, pd.Series(daily)

# QQQ sweep daily P&L for correlation
def qqq_daily():
    src = open("btc_sweep_test.py").read()  # not used; compute inline from full_yearly
    g={}; exec(open("full_yearly.py").read().split("# ── run all")[0], g)
    q=g["q"]; vmult=g["vmult"]; cap=10_000; rows={}; it=False; e=s=t=sh=0.; dt=None; cur=None; ds=cap; lock=False
    for i in range(1,len(q)):
        day=q["Date"].iloc[i]; price=float(q["Close"].iloc[i]); sig=int(q["S1"].iloc[i-1]); vm=vmult(q.index[i-1].date())
        if day!=cur: cur=day; ds=cap; lock=False
        if (cap-ds)/max(ds,1)<=-0.05 or (cap-10000)/10000<=-0.10: lock=True
        if lock: continue
        if it:
            if price<=s: p=sh*(s-e); cap+=p; rows[day]=rows.get(day,0)+p; it=False
            elif price>=t: p=sh*(t-e); cap+=p; rows[day]=rows.get(day,0)+p; it=False
        elif sig and vm>0 and dt!=day:
            it=True; dt=day; e=price; s=price*0.985; t=price*1.045; sh=(cap*0.007*vm)/(price*0.015)
    return pd.Series(rows)

print("="*66); print("SWEEP on index FUTURES (24h data, ~2y, net costs)"); print("="*66)
print(f"{'Future':<16}{'years...':>40}{'avg':>9}{'corr→QQQ':>10}")
print("-"*66)
qd = qqq_daily(); qd.index = pd.to_datetime(qd.index)
for tkr,name in [("NIY=F","Nikkei"),("RTY=F","Russell"),("YM=F","Dow")]:
    d=build(tkr); yrs,ser=run(d)
    avg=np.mean(list(yrs.values()))
    ser.index=pd.to_datetime(ser.index)
    idx=pd.bdate_range("2024-01-01","2026-06-28")
    a=ser.reindex(idx).fillna(0); b=qd.reindex(idx).fillna(0)
    corr=a.corr(b) if a.std()>0 and b.std()>0 else float("nan")
    ys="".join(f"{yrs.get(y,0):>+8.1%}" for y in sorted(yrs))
    print(f"{name:<16}{ys:>40}{avg:>+9.1%}{corr:>10.2f}")
print("-"*66)
print("Positive avg + low corr→QQQ = candidate pillar. (2y data = preliminary.)")
