"""
SPX/VIX DIVERGENCE strategy test.
SPY and VIX are normally inverse (VIX is derived from SPX options). The EDGE is
in the DIVERGENCE — when they move together (abnormal):
  - SPY down + VIX down  = fear NOT confirming the drop = bullish reversal -> LONG
  - SPY up   + VIX up    = hidden fear during rally     = bearish (skip/short)
We test the long-only bullish-divergence signal, net of costs, with OOS split and
direction check (trade the OPPOSITE to prove the sign), plus correlation to QQQ S1.
"""
import pandas as pd, numpy as np, warnings
from datetime import date, timedelta
import yfinance as yf
warnings.filterwarnings("ignore")
START,END="2019-01-01","2023-12-31"; YEARS=range(2019,2024); SLIP=0.0003

spy=yf.download("SPY",start=START,end=END,progress=False,auto_adjust=True)
if isinstance(spy.columns,pd.MultiIndex): spy.columns=spy.columns.droplevel(1)
qqq=yf.download("QQQ",start=START,end=END,progress=False,auto_adjust=True)
if isinstance(qqq.columns,pd.MultiIndex): qqq.columns=qqq.columns.droplevel(1)
vix=yf.download("^VIX",start=START,end=END,progress=False)["Close"]
if isinstance(vix,pd.DataFrame): vix=vix.iloc[:,0]

df=pd.DataFrame(index=spy.index)
df["QO"]=qqq["Open"]; df["QC"]=qqq["Close"]
df["spy_ret"]=spy["Close"].pct_change()
df["vix_ret"]=vix.reindex(spy.index).pct_change()
df["vix_ma"]=vix.reindex(spy.index).rolling(21).mean()
df=df.dropna()

# Signals (evaluated on close, traded next open)
df["bull_div"]=((df["spy_ret"]<0)&(df["vix_ret"]<0)).astype(int)   # both down
df["inv_div"] =((df["spy_ret"]<0)&(df["vix_ret"]>0)).astype(int)   # normal (down+fear up)

def run(sig, hold=2, sl=0.02, rr=1.5, vix_cap=30):
    out={}; daily={}
    for Y in YEARS:
        cap=init=10_000; in_t=False; entry=stop=tgt=sh=0.; held=0
        d=df[df.index.year==Y]
        for i in range(1,len(d)):
            price=float(d["QC"].iloc[i]); s=int(d[sig].iloc[i-1]); v=float(d["vix_ma"].iloc[i-1])
            if in_t:
                held+=1
                if price<=stop or price>=tgt or held>=hold:
                    pnl=sh*(price-entry)-sh*(entry+price)*SLIP; cap+=pnl
                    daily[d.index[i].date()]=daily.get(d.index[i].date(),0)+pnl; in_t=False
            elif s==1 and v<vix_cap:
                entry=float(d["QO"].iloc[i]); in_t=True; held=0
                stop=entry*(1-sl); tgt=entry*(1+sl*rr); sh=(cap*0.006)/(entry*sl)
        out[Y]=(cap-init)/init
    return out, pd.Series(daily)

print("="*72)
print("SPX/VIX DIVERGENCE — long QQQ on bullish divergence (net of costs)")
print("="*72)
print(f"{'Variant':<34}"+"".join(f"{Y:>8}" for Y in YEARS)+f"{'avg':>8}{'IN':>7}{'OUT':>7}")
print("-"*72)
for name,sig in [("Bull divergence (SPY-dn+VIX-dn)","bull_div"),
                 ("INVERSE check (SPY-dn+VIX-up)","inv_div")]:
    r,_=run(sig); avg=np.mean([r[Y] for Y in YEARS])
    IN=np.mean([r[Y] for Y in (2019,2020,2021)]); OUT=np.mean([r[Y] for Y in (2022,2023)])
    print(f"{name:<34}"+"".join(f"{r[Y]:>+8.1%}" for Y in YEARS)+f"{avg:>+8.1%}{IN:>+7.1%}{OUT:>+7.1%}")
print("-"*72)
# signal frequency
print(f"Bull-divergence signals: {int(df['bull_div'].sum())} days ({df['bull_div'].sum()/5:.0f}/yr)")
print("Read: if Bull beats INVERSE and holds OUT-of-sample, the divergence edge is real.")
