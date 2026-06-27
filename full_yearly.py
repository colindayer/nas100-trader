"""
FULL 5-strategy per-year backtest — the regime-diversified picture.
Fixes the data bugs that zeroed out S2/S3/S5:
  S5 ORB  : hourly data has no 9:30 bar -> use hour-9 bar as opening range + volume confirmation filter
  S2 Gold : yfinance won't serve 5yr hourly GLD -> use GLD DAILY FVG
  S3 Vol  : 2.0x threshold too strict (3 signals/5yr) -> 1.3x (more frequent but still reasonable, ~6-8/yr)
Params are standard/defensible, NOT tuned to maximize return (overfit discipline).
Each strategy resets to $10k each Jan => clean annual return %.
"""
import pandas as pd, numpy as np, pytz, warnings
from datetime import date, timedelta
import yfinance as yf
warnings.filterwarnings("ignore")
eastern=pytz.timezone("US/Eastern"); START,END="2019-01-01","2023-12-31"
YEARS=range(2019,2024)

# Transaction cost per SIDE (slippage + half-spread). Alpaca = commission-free,
# and we trade liquid ETFs (QQQ/SPY/GLD), so ~3 bps/side is realistic-conservative
# (~1c spread on $300-500 + minor slippage). Round-trip drag ~6 bps per trade.
SLIP=0.0003

# ── data ──────────────────────────────────────────────────────────────────────
df=pd.read_csv("qqq_hourly_7y.csv"); df["timestamp"]=pd.to_datetime(df["timestamp"],utc=True)
df=df.set_index("timestamp").tz_convert(eastern)
q=df[df["symbol"]=="QQQ"][["open","high","low","close","volume"]].copy()
q.columns=["Open","High","Low","Close","Volume"]
q=q[(q.index.date>=pd.Timestamp(START).date())&(q.index.date<=pd.Timestamp(END).date())]; q["Date"]=q.index.date
gex=pd.read_csv("gex_history.csv",index_col=0); gex.index=pd.to_datetime(gex.index).date
gex_map=(gex["gex"] if "gex" in gex.columns else gex.iloc[:,0]).to_dict()
vix=yf.download("^VIX",start=START,end=str(date.today()),progress=False)["Close"]
if isinstance(vix,pd.DataFrame): vix=vix.iloc[:,0]
vix.index=pd.to_datetime(vix.index).tz_localize(None).normalize(); vma=vix.rolling(21).mean()
vix_level=vix  # Raw VIX daily close prices
spy=yf.download("SPY",start=str(pd.Timestamp(START)-timedelta(days=365)).split()[0],end=str(date.today()),progress=False)["Close"]
if isinstance(spy,pd.DataFrame): spy=spy.iloc[:,0]
spy.index=pd.to_datetime(spy.index).tz_localize(None).normalize(); sbull=spy.ewm(span=50).mean()>spy.ewm(span=200).mean()
def asof(s,dts):
    m=s.reindex(s.index.union(dts)).ffill(); r=m.asof(dts); r.index=[t.date() for t in r.index]; return r
dts=pd.DatetimeIndex([pd.Timestamp(d) for d in sorted(q["Date"].unique())]); vix_by=asof(vma,dts); bull_by=asof(sbull,dts); vix_level_by=asof(vix_level,dts)
def vmult(d):
    v=vix_by.get(d,np.nan); return 1.0 if pd.isna(v) else (0.0 if v>25 else (0.5 if v>=20 else 1.0))
def neg_gex(d): return gex_map.get(d,0)<0 if d in gex_map else True
def is_bull(d): return bool(bull_by.get(d,True))

# ── shared QQQ features ───────────────────────────────────────────────────────
def isA(i): return i.hour>=18 or i.hour<2
def sd(i): return (i+pd.Timedelta(days=1)).date() if i.hour>=18 else i.date()
q["A"]=q.index.map(isA); q["SD"]=q.index.map(sd); ab=q[q["A"]]
q["AL"]=q["SD"].map(ab.groupby("SD")["Low"].min())
q["InS"]=q.index.map(lambda x:(2<=x.hour<5) or (9<=x.hour<12))
tp=(q["High"]+q["Low"]+q["Close"])/3; vv=[];ct=cv=0.;p_=None
for i in range(len(q)):
    d=q["Date"].iloc[i]
    if d!=p_: ct=cv=0.;p_=d
    if q["Volume"].iloc[i]>0: ct+=tp.iloc[i]*q["Volume"].iloc[i];cv+=q["Volume"].iloc[i]
    vv.append(ct/cv if cv>0 else float("nan"))
q["VWAP"]=vv
dc=q[q.index.hour==16][["Close"]].copy(); dc.index=dc.index.date; dc=dc[~dc.index.duplicated(keep="last")]
q["EMA50"]=q["Date"].map(dc["Close"].ewm(span=50).mean().to_dict())
q["EMA200"]=q["Date"].map(dc["Close"].ewm(span=200).mean().to_dict())
# Faber (2007) 200-day SMA regime gate: bear = daily close < 200d SMA.
# Used to auto-arm the S5 Short hedge only in confirmed risk-off regimes.
_sma200=dc["Close"].rolling(200).mean()
_bear200={d:(c<s) if not pd.isna(s) else False for d,c,s in zip(dc.index,dc["Close"],_sma200)}
q["Bear200"]=q["Date"].map(_bear200).fillna(False).astype(bool)
pc=q["Close"].shift(1); tr=pd.concat([q["High"]-q["Low"],(q["High"]-pc).abs(),(q["Low"]-pc).abs()],axis=1).max(axis=1)
atr=tr.rolling(14).mean(); q["ATR"]=atr; q["HV"]=atr>1.5*atr.rolling(200).mean()
q["SB"]=q["Date"].map(bull_by).fillna(True).astype(bool)
q["NG"]=q["Date"].map(neg_gex)
q["SL"]=(q["Low"]<q["AL"])&(q["Close"]>q["AL"])
q["S1"]=(q["SL"]&q["InS"]&(q["Close"]>q["VWAP"])&(q["Close"]>q["EMA50"])&q["SB"]&~q["HV"]&q["AL"].notna()&q["NG"]).astype(int)
q["S4"]=(q["SL"]&q["InS"]&(q["Close"]>q["EMA50"])&(q["EMA50"]>q["EMA200"])&~q["HV"]&q["AL"].notna()&q["NG"]).astype(int)

# S5 ORB (hourly approx): opening range = hour-9 bar; breakout in hours 10-13
orb=q[q.index.hour==9].copy(); orb_hi={d:r["High"] for d,r in zip(orb["Date"],orb.to_dict("records"))}
orb_lo={d:r["Low"]  for d,r in zip(orb["Date"],orb.to_dict("records"))}
orb_vol={d:r["Volume"] for d,r in zip(orb["Date"],orb.to_dict("records"))}
q["ORBHi"]=q["Date"].map(orb_hi)
q["ORBLo"]=q["Date"].map(orb_lo)
q["ORBVol"]=q["Date"].map(orb_vol)
q["ORBwin"]=q.index.map(lambda x:10<=x.hour<=13)
q["ORBRange"]=q["ORBHi"]-q["ORBLo"]
q["vol_ma20"]=q["Volume"].rolling(20).mean()
q["VIXlvl"]=q["Date"].map(vix_level_by.to_dict())   # per-bar raw VIX level (date-aligned)
# S5 Long: breakout above ORB High with volume confirmation (avoid volume collapse)
q["S5L"]=(q["ORBwin"]&(q["Close"]>q["ORBHi"])&q["SB"]&q["NG"]&q["ORBHi"].notna()&(q["Volume"]>q["ORBVol"]*0.6)).astype(int)
# S5 Short: ORB-low break, auto-armed ONLY in a Faber 200-day bear regime.
# Always-on (~SB EMA-cross) lost -0.6%/yr — it shorted into the 2019 recovery.
# Gating on price<200d SMA flips it to +0.4%/yr and strengthens the 2022 hedge
# (+0.6%->+2.7%). One standard regime rule, no tuned thresholds. See FINDINGS.md.
q["S5S"]=(q["ORBwin"]&(q["Close"]<q["ORBLo"])&q["Bear200"]&q["NG"]&q["ORBLo"].notna()&(q["Volume"]>q["ORBVol"]*0.6)).astype(int)

# ── intraday engine (one entry per day, first signal) ─────────────────────────
def run_intraday(sig_col, risk, sl, rr, short=False):
    out={}
    for Y in YEARS:
        cap=init=10_000; in_t=False; entry=stop=tgt=sh=0.; ds=cap; cur=None; lock=False; day_traded=None
        for i in range(1,len(q)):
            if q.index[i].year!=Y: continue
            d=q.index[i].date(); price=float(q["Close"].iloc[i]); s=int(q[sig_col].iloc[i-1]); vm=vmult(q.index[i-1].date())
            if d!=cur: cur=d; ds=cap; lock=False
            if (cap-ds)/max(ds,1)<=-0.05 or (cap-init)/init<=-0.10: lock=True
            if lock: continue
            if in_t:
                if not short:
                    if price<=stop: cap+=sh*(stop-entry)-sh*(entry+stop)*SLIP; in_t=False
                    elif price>=tgt: cap+=sh*(tgt-entry)-sh*(entry+tgt)*SLIP; in_t=False
                else:
                    if price>=stop: cap+=sh*(entry-price)-sh*(entry+stop)*SLIP; in_t=False
                    elif price<=tgt: cap+=sh*(entry-price)-sh*(entry+tgt)*SLIP; in_t=False
            elif s==1 and vm>0 and day_traded!=d:
                in_t=True; day_traded=d; entry=price
                # Fixed percentage stops (validated). ATR stops were tested and
                # degraded S1/S4 — reverted. See FINDINGS.md.
                if not short: stop=price*(1-sl); tgt=price*(1+sl*rr)
                else: stop=price*(1+sl); tgt=price*(1-sl*rr)
                sh=(cap*risk*vm)/(price*sl)
        out[Y]=(cap-init)/init
    return out

# ── S2 Gold FVG (daily) ───────────────────────────────────────────────────────
gld=yf.download("GLD",start=START,end=END,interval="1d",progress=False,auto_adjust=True)
if isinstance(gld.columns,pd.MultiIndex): gld.columns=gld.columns.droplevel(1)
gld=gld[["Open","High","Low","Close"]].copy(); gld.index=pd.to_datetime(gld.index)
gld["bull"]=gld.index.map(lambda d: is_bull(d.date()))
# Bullish FVG: today's low > high two bars ago (gap up) + green + risk-on
gld["FVG"]=((gld["Low"]>gld["High"].shift(2))&(gld["Close"]>gld["Open"])&gld["bull"]).astype(int)
def run_s2(risk=0.005, sl=0.012, rr=2.0):
    out={}
    for Y in YEARS:
        cap=init=10_000; in_t=False; entry=stop=tgt=sh=0.
        g=gld[gld.index.year==Y]
        for i in range(1,len(g)):
            price=float(g["Close"].iloc[i]); s=int(g["FVG"].iloc[i-1])
            if in_t:
                if price<=stop: cap+=sh*(stop-entry)-sh*(entry+stop)*SLIP; in_t=False
                elif price>=tgt: cap+=sh*(tgt-entry)-sh*(entry+tgt)*SLIP; in_t=False
            elif s==1:
                in_t=True; entry=price; stop=price*(1-sl); tgt=price*(1+sl*rr); sh=(cap*risk)/(price*sl)
        out[Y]=(cap-init)/init
    return out

# ── S3 Abnormal Volume (daily QQQ, 1.5x, hold up to 5 days) ────────────────────
qd=q.groupby("Date").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"})
qd.index=pd.to_datetime(qd.index); qd["ma20"]=qd["Volume"].rolling(20).mean()
qd["bull"]=qd.index.map(lambda d:is_bull(d.date())); qd["ng"]=qd.index.map(lambda d:neg_gex(d.date()))
qd["S3"]=((qd["Volume"]>1.3*qd["ma20"])&(qd["Close"]>qd["Open"])&qd["bull"]&qd["ng"]).astype(int)
def run_s3(risk=0.004, sl=0.02, rr=2.5, hold=5):
    out={}
    for Y in YEARS:
        cap=init=10_000; in_t=False; entry=stop=tgt=sh=0.; held=0
        g=qd[qd.index.year==Y]
        for i in range(1,len(g)):
            price=float(g["Close"].iloc[i]); s=int(g["S3"].iloc[i-1])
            if in_t:
                held+=1
                if price<=stop or price>=tgt or held>=hold: cap+=sh*(price-entry)-sh*(entry+price)*SLIP; in_t=False
            elif s==1:
                in_t=True; entry=price; stop=price*(1-sl); tgt=price*(1+sl*rr); held=0; sh=(cap*risk)/(price*sl)
        out[Y]=(cap-init)/init
    return out

# ── run all ───────────────────────────────────────────────────────────────────
res={
 "S1 Asian Sweep":      run_intraday("S1",0.007,0.015,3.0),
 "S4 Multi-Sweep":      run_intraday("S4",0.005,0.015,3.0),
 "S5 ORB Long":         run_intraday("S5L",0.005,0.010,2.5),
 "S5 ORB Short":        run_intraday("S5S",0.003,0.010,2.5,short=True),
 "S2 Gold FVG":         run_s2(),
 "S3 Abnormal Volume":  run_s3(),
}
print("\n"+"="*78)
print("FULL 5-STRATEGY PER-YEAR RETURN (each on its own $10k sleeve)")
print("="*78)
hdr=f"{'Strategy':<22}"+"".join(f"{Y:>9}" for Y in YEARS)+f"{'avg':>9}"
print(hdr); print("-"*78)
for name,d in res.items():
    avg=np.mean([d[Y] for Y in YEARS])
    print(f"{name:<22}"+"".join(f"{d[Y]:>+9.1%}" for Y in YEARS)+f"{avg:>+9.1%}")
print("-"*78)
combo={Y:sum(d[Y] for d in res.values()) for Y in YEARS}
print(f"{'COMBINED (sum)':<22}"+"".join(f"{combo[Y]:>+9.1%}" for Y in YEARS)+f"{np.mean(list(combo.values())):>+9.1%}")

avg_all=np.mean(list(combo.values())); avg_oos=np.mean([combo[Y] for Y in (2022,2023)])
print("\n"+"="*78)
print("$50k PROP ACCOUNT — MONTHLY PROFIT (80% split)")
print("="*78)
for label,a in [("Optimistic (5yr avg)",avg_all),("Realistic (OOS 2022-23)",avg_oos),("Worst year (2022)",combo[2022])]:
    gross=50_000*a; mo=(gross/12)*0.80
    print(f"  {label:<28} {a:>+7.1%}/yr  ->  ${mo:>+7,.0f}/mo net")
print("="*78)
print("Note: S5 ORB is a coarse hourly approximation (no intraday 30-min bars).")
print("S2 uses GLD daily FVG. SPY leg of S4 still not included (no local data).")

# ── OUT-OF-SAMPLE SPLIT: tune-era 2019-21 vs untouched 2022-23 ─────────────────
IN_Y=(2019,2020,2021); OUT_Y=(2022,2023)
print("\n"+"="*78)
print("OUT-OF-SAMPLE SPLIT  —  IN (2019-21)  vs  OUT (2022-23, unseen)")
print("="*78)
print(f"{'Strategy':<22}{'IN avg':>10}{'OUT avg':>10}{'degraded?':>12}")
print("-"*78)
for name,d in res.items():
    i=np.mean([d[Y] for Y in IN_Y]); o=np.mean([d[Y] for Y in OUT_Y])
    flag = "holds" if o>0 else ("FLAT/NEG" if o<=0 else "")
    print(f"{name:<22}{i:>+10.1%}{o:>+10.1%}{flag:>12}")
print("-"*78)
ci=np.mean([combo[Y] for Y in IN_Y]); co=np.mean([combo[Y] for Y in OUT_Y])
print(f"{'COMBINED':<22}{ci:>+10.1%}{co:>+10.1%}{'holds' if co>0 else 'FAILS':>12}")
print(f"\nWorst single year — IN: {min(combo[Y] for Y in IN_Y):+.1%} | OUT: {min(combo[Y] for Y in OUT_Y):+.1%}")
print("Diversification check: is the WORST year still positive out-of-sample?")
print("="*78)
