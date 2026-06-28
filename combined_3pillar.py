"""
THE CAPSTONE: full 3-pillar system on ONE shared account.
Pillar 1+2 = Nasdaq (S1,S4,S5L,S5S hourly) + Gold (FVG)  — from full_yearly
Pillar 3   = BTC sweep (2.5% stop)                        — from btc_1h.csv
All net of costs. Measures combined return, Sharpe, and max drawdown — to see
whether the 3rd uncorrelated pillar tightens the -16% tail.
"""
import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")

# ── Pillars 1+2: Nasdaq + Gold (compute BEFORE BTC exec, so SLIP=ETF 3bps) ─────
exec(open("full_yearly.py").read().split("# ── run all")[0])  # q, gld, vmult, SLIP, YEARS

def trades_intraday(sig, risk, sl, rr, short=False):
    cap=10_000; rows=[]; it=False; e=s=t=sh=0.; ds=cap; cur=None; lock=False; dt=None
    for i in range(1,len(q)):
        dd=q.index[i].date(); price=float(q["Close"].iloc[i]); g=int(q[sig].iloc[i-1]); vm=vmult(q.index[i-1].date())
        if dd!=cur: cur=dd; ds=cap; lock=False
        if (cap-ds)/max(ds,1)<=-0.05 or (cap-10_000)/10_000<=-0.10: lock=True
        if lock: continue
        if it:
            p=None
            if not short:
                if price<=s: p=sh*(s-e)-sh*(e+s)*SLIP
                elif price>=t: p=sh*(t-e)-sh*(e+t)*SLIP
            else:
                if price>=s: p=sh*(e-price)-sh*(e+s)*SLIP
                elif price<=t: p=sh*(e-price)-sh*(e+t)*SLIP
            if p is not None: cap+=p; rows.append((dd,p)); it=False
        elif g and vm>0 and dt!=dd:
            it=True; dt=dd; e=price
            if not short: s=price*(1-sl); t=price*(1+sl*rr)
            else: s=price*(1+sl); t=price*(1-sl*rr)
            sh=(cap*risk*vm)/(price*sl)
    return rows

def trades_gold(risk=0.005, sl=0.012, rr=2.0):
    cap=10_000; rows=[]; it=False; e=s=t=sh=0.
    for i in range(1,len(gld)):
        price=float(gld["Close"].iloc[i]); g=int(gld["FVG"].iloc[i-1]); dd=gld.index[i].date()
        if it:
            if price<=s: p=sh*(s-e)-sh*(e+s)*SLIP; cap+=p; rows.append((dd,p)); it=False
            elif price>=t: p=sh*(t-e)-sh*(e+t)*SLIP; cap+=p; rows.append((dd,p)); it=False
        elif g: it=True; e=price; s=price*(1-sl); t=price*(1+sl*rr); sh=(cap*risk)/(price*sl)
    return rows

nasdaq = (trades_intraday("S1",0.007,0.015,3.0) + trades_intraday("S4",0.005,0.015,3.0) +
          trades_intraday("S5L",0.005,0.010,2.5) + trades_intraday("S5S",0.003,0.010,2.5,short=True))
gold = trades_gold()

def daily(rows):
    s = pd.Series(0.0, index=[])
    by = {}
    for dd,p in rows: by[pd.Timestamp(dd)] = by.get(pd.Timestamp(dd),0)+p
    return pd.Series(by).sort_index()

nasdaq_d = daily(nasdaq); gold_d = daily(gold)

# ── Pillar 3: BTC (exec overwrites q/d/SLIP — fine, Nasdaq already computed) ────
exec(open("btc_sweep_test.py").read().split("def run(sl")[0])  # d (BTC, sig), SLIP=0.0004
def trades_btc(sl=0.025, rr=3.0, risk=0.006):
    cap=10_000; rows=[]; it=False; e=s=t=sh=0.; dt=None; ds=cap; cur=None; lock=False
    for i in range(1,len(d)):
        dd=d["Date"].iloc[i]; price=float(d["Close"].iloc[i]); g=int(d["sig"].iloc[i-1])
        if dd!=cur: cur=dd; ds=cap; lock=False
        if (cap-ds)/max(ds,1)<=-0.05 or (cap-10_000)/10_000<=-0.10: lock=True
        if lock: continue
        if it:
            if price<=s: p=sh*(s-e)-sh*(e+s)*SLIP; cap+=p; rows.append((dd,p)); it=False
            elif price>=t: p=sh*(t-e)-sh*(e+t)*SLIP; cap+=p; rows.append((dd,p)); it=False
        elif g and dt!=dd:
            it=True; dt=dd; e=price; s=price*(1-sl); t=price*(1+sl*rr); sh=(cap*risk)/(price*sl)
    return rows
btc_d = daily(trades_btc())

# ── Combine on ONE $10k account ───────────────────────────────────────────────
def kpis(pnl_daily, label, base=10_000):
    pnl_daily = pnl_daily.sort_index()
    idx = pd.date_range(pnl_daily.index.min(), pnl_daily.index.max(), freq="D")
    pnl = pnl_daily.reindex(idx).fillna(0.0)
    eq = base + pnl.cumsum()
    rets = eq.pct_change().fillna(0)
    yrs = (eq.index[-1]-eq.index[0]).days/365.25
    cagr = (eq.iloc[-1]/base)**(1/yrs)-1
    sharpe = (rets.mean()*252)/(rets.std()*np.sqrt(252)) if rets.std()>0 else 0
    mdd = ((eq-eq.cummax())/eq.cummax()).min()
    tot = (eq.iloc[-1]/base-1)
    print(f"  {label:<24} CAGR {cagr:>+6.1%} | Sharpe {sharpe:>4.2f} | MaxDD {mdd:>+6.1%} | total {tot:>+7.1%}")
    return pnl

print("\n"+"="*72)
print("3-PILLAR SYSTEM — individual vs combined (one $10k account, net of costs)")
print("="*72)
kpis(nasdaq_d, "Nasdaq (S1+S4+S5)")
kpis(gold_d,   "Gold (FVG)")
kpis(btc_d,    "BTC (sweep)")
print("-"*72)
combined = pd.concat([nasdaq_d, gold_d, btc_d]).groupby(level=0).sum()
kpis(combined, "★ COMBINED 3-PILLAR")
print("="*72)
print("If COMBINED MaxDD is shallower than the worst single pillar, diversification")
print("is doing its job — the 3rd uncorrelated pillar tightens the tail.")
