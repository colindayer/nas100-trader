"""
BTC sweep — the decisive gauntlet: walk-forward, decay split, correlation to QQQ.
Uses the vol-scaled 2.5% stop. Determines if BTC is a real pillar #3 or a fading edge.
"""
import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
_src = open("btc_sweep_test.py").read().split("def run(sl")[0]
exec(_src)   # builds `d` (BTC 1h with sweep signal) + SLIP

SL, RR, RISK = 0.025, 3.0, 0.006

def btc_trades():
    """Continuous BTC sweep over full period; return list of (date, pnl)."""
    cap = 10_000; rows = []; it=False; e=s=t=sh=0.; dt=None; ds=cap; cur=None; lock=False
    for i in range(1, len(d)):
        day = d["Date"].iloc[i]; price = float(d["Close"].iloc[i]); g = int(d["sig"].iloc[i-1])
        if day != cur: cur=day; ds=cap; lock=False
        if (cap-ds)/max(ds,1) <= -0.05 or (cap-10_000)/10_000 <= -0.10: lock=True
        if lock: continue
        if it:
            if price <= s: pnl=sh*(s-e)-sh*(e+s)*SLIP; cap+=pnl; rows.append((day,pnl)); it=False
            elif price >= t: pnl=sh*(t-e)-sh*(e+t)*SLIP; cap+=pnl; rows.append((day,pnl)); it=False
        elif g and dt != day:
            it=True; dt=day; e=price; s=price*(1-SL); t=price*(1+SL*RR); sh=(cap*RISK)/(price*SL)
    return rows

bt = btc_trades()
bpnl = pd.Series({pd.Timestamp(dd): 0.0 for dd,_ in bt})
for dd,p in bt: bpnl[pd.Timestamp(dd)] += p
bpnl = bpnl.sort_index()

# ── 1. Walk-forward (rolling 6-month test windows) ────────────────────────────
print("="*64); print("BTC SWEEP VALIDATION (2.5% stop, net of costs)"); print("="*64)
print("\n[1] Rolling 6-month windows (consistency / decay):")
eq = 10_000 + bpnl.cumsum()
starts = pd.date_range(bpnl.index.min().normalize(), bpnl.index.max(), freq="6MS")
pos = 0; tot = 0
for s0 in starts:
    s1 = s0 + pd.DateOffset(months=6)
    w = bpnl[(bpnl.index >= s0) & (bpnl.index < s1)]
    if len(w) < 3: continue
    r = w.sum() / 10_000; tot += 1; pos += (r > 0)
    print(f"  {s0.date()} → {s1.date()}: {r:>+6.1%}  ({len(w)} trade-days)")
print(f"  Positive windows: {pos}/{tot} ({100*pos/max(tot,1):.0f}%)")

# ── 2. Decay split ────────────────────────────────────────────────────────────
early = bpnl[bpnl.index.year <= 2021].sum()/10_000
recent = bpnl[bpnl.index.year >= 2023].sum()/10_000
ny_e = len(set(bpnl[bpnl.index.year <= 2021].index.year))
ny_r = len(set(bpnl[bpnl.index.year >= 2023].index.year))
print(f"\n[2] Decay check:")
print(f"  2019-2021 (early crypto): {early:+.1%} total = {early/ny_e:+.1%}/yr")
print(f"  2023-2026 (mature crypto): {recent:+.1%} total = {recent/ny_r:+.1%}/yr")
print(f"  -> {'STILL ALIVE' if recent/ny_r > 0.02 else 'DECAYED — caution'}")

# ── 3. Correlation to QQQ sweep (the diversification point) ────────────────────
print(f"\n[3] Correlation to QQQ sweep (diversification check):")
try:
    _q = open("full_yearly.py").read().split("# ── run all")[0]; ns={}; exec(_q, ns)
    q=ns["q"]; vmult=ns["vmult"]; SLIPq=ns["SLIP"]
    cap=10_000; qrows=[]; it=False; e=s=t=sh=0.; dt=None; cur=None; ds=cap; lock=False
    for i in range(1,len(q)):
        day=q["Date"].iloc[i]; price=float(q["Close"].iloc[i]); g=int(q["S1"].iloc[i-1]); vm=vmult(q.index[i-1].date())
        if day!=cur: cur=day; ds=cap; lock=False
        if (cap-ds)/max(ds,1)<=-0.05 or (cap-10_000)/10_000<=-0.10: lock=True
        if lock: continue
        if it:
            if price<=s: pnl=sh*(s-e)-sh*(e+s)*SLIPq; cap+=pnl; qrows.append((day,pnl)); it=False
            elif price>=t: pnl=sh*(t-e)-sh*(e+t)*SLIPq; cap+=pnl; qrows.append((day,pnl)); it=False
        elif g and vm>0 and dt!=day:
            it=True; dt=day; e=price; s=price*(1-0.015); t=price*(1+0.015*3); sh=(cap*0.007*vm)/(price*0.015)
    qpnl=pd.Series({pd.Timestamp(dd):0.0 for dd,_ in qrows})
    for dd,p in qrows: qpnl[pd.Timestamp(dd)]+=p
    idx=pd.bdate_range("2019-01-01","2026-06-28")
    a=bpnl.reindex(idx).fillna(0); b=qpnl.reindex(idx).fillna(0)
    corr=a.corr(b)
    print(f"  corr(BTC sweep, QQQ sweep) daily P&L = {corr:+.3f}")
    print(f"  -> {'UNCORRELATED — genuine diversifier ✅' if abs(corr)<0.2 else 'correlated — adds less'}")
except Exception as ex:
    print(f"  (QQQ correlation skipped: {ex})")
print("="*64)
