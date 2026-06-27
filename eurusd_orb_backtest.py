"""
EURUSD Opening-Range Breakout — our PROVEN S5 ORB edge applied to a prop-firm
instrument (EURUSD / euro futures). Mirrors the TradingView "EURUSD strategy"
(Kaspricci): NY-open opening range, breakout both directions, ATR stops.

Data: yfinance EURUSD=X hourly (~2.75y, 2023-2026). Net of costs (~1bp/side,
EURUSD spread is tight). IN/OUT split + direction sanity (long vs short legs).
This is the RIGHT kind of expansion: reuse a validated mechanism (ORB), not a
new untested edge. Still must prove out — same discipline as everything else.
"""
import pandas as pd, numpy as np, warnings
import yfinance as yf
warnings.filterwarnings("ignore")
SLIP=0.0001  # ~1 pip round-trip-ish on EURUSD (tight); conservative

d=yf.download("EURUSD=X",period="730d",interval="1h",progress=False)
if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.droplevel(1)
d=d[["Open","High","Low","Close"]].copy()
d.index=pd.to_datetime(d.index)
if d.index.tz is None: d.index=d.index.tz_localize("UTC")
else: d.index=d.index.tz_convert("UTC")
d["Date"]=d.index.date; d["H"]=d.index.hour

# ATR(14) on hourly
pc=d["Close"].shift(1)
tr=pd.concat([d["High"]-d["Low"],(d["High"]-pc).abs(),(d["Low"]-pc).abs()],axis=1).max(axis=1)
d["ATR"]=tr.rolling(14).mean()

# Opening range = NY open hour (13:00 UTC bar). Breakout window 14:00-20:00 UTC.
OR_HOUR=13
orb=d[d["H"]==OR_HOUR]
orb_hi={dt:r["High"] for dt,r in zip(orb["Date"],orb.to_dict("records"))}
orb_lo={dt:r["Low"]  for dt,r in zip(orb["Date"],orb.to_dict("records"))}
d["ORBHi"]=d["Date"].map(orb_hi); d["ORBLo"]=d["Date"].map(orb_lo)
d["win"]=(d["H"]>=14)&(d["H"]<=20)

def run(direction):  # 'long','short','both'
    """One trade/day max. ATR(2x) stop, 2:1 target, close at session end (H>20)."""
    yrs={}; daily={}
    for Y in sorted(set(d.index.year)):
        cap=init=10_000; in_t=False; entry=stop=tgt=sh=0.; side=0; dt=None
        dd=d[d.index.year==Y]
        for i in range(1,len(dd)):
            row=dd.iloc[i]; price=float(row["Close"]); day=row["Date"]; h=row["H"]
            atr=float(dd["ATR"].iloc[i-1]) if not pd.isna(dd["ATR"].iloc[i-1]) else None
            if in_t:
                exit_now=False; px=price
                if side>0:
                    if price<=stop: px=stop; exit_now=True
                    elif price>=tgt: px=tgt; exit_now=True
                else:
                    if price>=stop: px=stop; exit_now=True
                    elif price<=tgt: px=tgt; exit_now=True
                if h>20: exit_now=True   # close at session end
                if exit_now:
                    pnl=sh*((px-entry) if side>0 else (entry-px))-sh*(entry+px)*SLIP
                    cap+=pnl; daily[day]=daily.get(day,0)+pnl; in_t=False
            elif bool(row["win"]) and dt!=day and atr and not pd.isna(row["ORBHi"]):
                up=price>row["ORBHi"]; dn=price<row["ORBLo"]
                go_long = up and direction in ("long","both")
                go_short= dn and direction in ("short","both")
                if go_long or go_short:
                    in_t=True; dt=day; entry=price; side=1 if go_long else -1
                    stop=entry-side*atr*2; tgt=entry+side*atr*2*2.0
                    sh=(cap*0.01)/(atr*2)   # risk 1% per trade
        yrs[Y]=(cap-init)/init
    return yrs

print("="*64)
print("EURUSD ORB (NY open) — our S5 edge on a prop instrument, net of costs")
print("="*64)
yrs=sorted(set(d.index.year))
print(f"{'Direction':<12}"+"".join(f"{y:>9}" for y in yrs)+f"{'avg':>9}")
print("-"*64)
for dir_ in ["both","long","short"]:
    r=run(dir_); avg=np.mean(list(r.values()))
    print(f"{dir_:<12}"+"".join(f"{r.get(y,0):>+9.1%}" for y in yrs)+f"{avg:>+9.1%}")
print("-"*64)
print("Data ~2.75y (2023-2026). First/last years partial. 'both'=long+short legs.")
print("Read: consistently positive across years = the ORB edge ports to EURUSD.")
