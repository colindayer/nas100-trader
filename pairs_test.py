"""
Pairs / correlation mean-reversion — a DIFFERENT edge type (market-neutral, not
directional). When two correlated assets' ratio diverges from its mean, bet on
convergence (long the laggard, short the leader). Structurally uncorrelated to the
directional sweeps. Net of costs. + correlation to QQQ sweep (the diversification test).
"""
import pandas as pd, numpy as np, yfinance as yf, warnings
warnings.filterwarnings("ignore")
COST = 0.0005  # per leg per turnover

def get(tkr, start="2015-01-01"):
    d = yf.download(tkr, start=start, end="2026-06-28", progress=False, auto_adjust=True)
    if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.droplevel(1)
    return d["Close"].dropna()

def pairs(a_tkr, b_tkr, name, win=60, z_in=2.0, z_out=0.5, start="2015-01-01"):
    A=get(a_tkr,start); B=get(b_tkr,start)
    df=pd.concat([A,B],axis=1).dropna(); df.columns=["A","B"]
    ratio=np.log(df["A"]/df["B"])
    z=(ratio-ratio.rolling(win).mean())/ratio.rolling(win).std()
    pos=pd.Series(0.0,index=df.index); cur=0
    for i in range(len(df)):
        zi=z.iloc[i]
        if cur==0:
            if zi> z_in: cur=-1   # ratio high -> short A long B
            elif zi<-z_in: cur=+1 # ratio low  -> long A short B
        else:
            if abs(zi)<z_out: cur=0
        pos.iloc[i]=cur
    retA=df["A"].pct_change().fillna(0); retB=df["B"].pct_change().fillna(0)
    pos_l=pos.shift(1).fillna(0)                     # trade next day (no lookahead)
    gross=pos_l*(retA-retB)
    turn=pos_l.diff().abs().fillna(0)
    pnl=gross - COST*2*turn                          # both legs
    cum=(1+pnl).cumprod(); yrs=(df.index[-1]-df.index[0]).days/365.25
    cagr=cum.iloc[-1]**(1/yrs)-1 if yrs>0 else 0
    sh=pnl.mean()/pnl.std()*np.sqrt(252) if pnl.std() else 0
    mdd=(cum/cum.cummax()-1).min()
    return name,cagr,sh,mdd,pnl

# QQQ sweep daily P&L (for correlation)
g={}; exec(open("full_yearly.py").read().split("# ── run all")[0], g)
q=g["q"]; vm=g["vmult"]; cap=10000; rows={}; it=False; e=s=t=sh=0.; dt=None; cur=None; ds=cap; lock=False
for i in range(1,len(q)):
    day=q["Date"].iloc[i]; price=float(q["Close"].iloc[i]); sig=int(q["S1"].iloc[i-1]); v=vm(q.index[i-1].date())
    if day!=cur: cur=day; ds=cap; lock=False
    if (cap-ds)/max(ds,1)<=-0.05 or (cap-10000)/10000<=-0.10: lock=True
    if lock: continue
    if it:
        if price<=s: p=sh*(s-e); cap+=p; rows[day]=rows.get(day,0)+p; it=False
        elif price>=t: p=sh*(t-e); cap+=p; rows[day]=rows.get(day,0)+p; it=False
    elif sig and v>0 and dt!=day:
        it=True; dt=day; e=price; s=price*0.985; t=price*1.045; sh=(cap*0.007*v)/(price*0.015)
qd=pd.Series(rows); qd.index=pd.to_datetime(qd.index)

print("="*70); print("PAIRS mean-reversion (market-neutral, net costs)"); print("="*70)
print(f"{'Pair':<22}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'corr→QQQsweep':>15}")
print("-"*70)
for a,b,nm,st in [("GLD","SLV","Gold/Silver","2015-01-01"),
                  ("QQQ","SPY","Nasdaq/S&P","2015-01-01"),
                  ("XLE","XLF","Energy/Financ","2015-01-01"),
                  ("BTC-USD","ETH-USD","BTC/ETH","2018-01-01")]:
    try:
        nm2,c,s,m,pnl=pairs(a,b,nm,start=st)
        idx=pd.bdate_range("2019-01-01","2023-12-31")
        ca=pnl.reindex(idx).fillna(0); cb=qd.reindex(idx).fillna(0)
        corr=ca.corr(cb) if ca.std()>0 and cb.std()>0 else float("nan")
        print(f"{nm:<22}{c:>+8.1%}{s:>8.2f}{m:>+8.1%}{corr:>15.2f}")
    except Exception as ex:
        print(f"{nm:<22}  failed: {str(ex)[:30]}")
print("-"*70)
print("Want: positive Sharpe AND low corr→QQQ (different edge type = real diversifier).")
