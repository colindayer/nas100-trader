"""
multi_asset_orb.py — Does the ORB break-retest concept TRAVEL to other asset
classes? Edges are instrument-specific, so a concept dead on QQQ may live on
oil/gold/bonds. We pull hourly data (~2yr, all yfinance gives at this grain) for
a diverse basket and run the same ORB-retest on each. Coarser + shorter window
than ideal, so treat as a SCREEN — survivors get a proper fine-grained test.
"""
import pandas as pd, numpy as np, pytz, warnings
import yfinance as yf
from datetime import date
warnings.filterwarnings("ignore")
eastern = pytz.timezone("US/Eastern")
SLIP, RR = 0.0005, 2.0

UNIVERSE = {
    "USO": "oil", "GLD": "gold", "SLV": "silver", "TLT": "bonds",
    "UNG": "natgas", "DBA": "agriculture", "QQQ": "nasdaq(ref)", "GDX": "goldminers",
}


def load(sym):
    d = yf.download(sym, period="730d", interval="1h", progress=False, auto_adjust=True)
    if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    d = d.tz_convert(eastern) if d.index.tz else d.tz_localize("UTC").tz_convert(eastern)
    d = d[(d.index.hour >= 9) & (d.index.hour < 16)].copy()
    d["Date"] = d.index.date; d["t"] = d.index.hour*60 + d.index.minute
    return d[["Open","High","Low","Close","Volume","Date","t"]]


def run_orb_retest(data):
    trades = []
    for d, g in data.groupby("Date"):
        orb = g[g["t"] < 600]                 # first session hour(s) ≤10:00
        if len(orb) < 1: continue
        orh, orl = orb["High"].max(), orb["Low"].min()
        if orh <= orl: continue
        post = g[g["t"] >= 600]
        armed = False; entry = stop = tgt = None
        for _, r in post.iterrows():
            if entry is None:
                if not armed and r["Close"] > orh: armed = True
                elif armed and r["Low"] <= orh and r["Close"] > orh:
                    entry = r["Close"]; stop = orl; tgt = entry + RR*(entry-orl)
            else:
                if r["Low"] <= stop: trades.append(-(entry-stop)/entry - SLIP); entry=None; break
                if r["High"] >= tgt: trades.append((tgt-entry)/entry - SLIP); entry=None; break
        if entry is not None:
            trades.append((post["Close"].iloc[-1]-entry)/entry - SLIP)
    return trades


def m(trades):
    t = pd.Series(trades)
    if len(t) < 10: return None
    eq = (1+t).cumprod(); yrs = 2.0
    return dict(n=len(t), wr=(t>0).mean(), ret=eq.iloc[-1]-1,
                sharpe=t.mean()/t.std()*np.sqrt(len(t)/yrs) if t.std()>0 else 0,
                dd=(eq/eq.cummax()-1).min())


print("ORB break-retest across asset classes (hourly, ~2yr SCREEN)\n")
print(f"{'Asset':<6}{'class':<14}{'n':>5}{'win':>6}{'ret':>9}{'Sharpe':>8}{'maxDD':>8}  verdict")
print("-"*70)
results = []
for sym, cls in UNIVERSE.items():
    try:
        s = m(run_orb_retest(load(sym)))
    except Exception as e:
        print(f"{sym:<6}{cls:<14} data error: {type(e).__name__}"); continue
    if s is None:
        print(f"{sym:<6}{cls:<14} too few trades"); continue
    good = s["sharpe"] > 0.5 and s["ret"] > 0
    results.append((sym, cls, s, good))
    print(f"{sym:<6}{cls:<14}{s['n']:>5}{s['wr']:>5.0%}{s['ret']:>+8.1%}"
          f"{s['sharpe']:>8.2f}{s['dd']:>7.1%}  {'PROMISING' if good else '—'}")
print("-"*70)
winners = [r for r in results if r[3]]
if winners:
    print(f"\nPromising on screen: {', '.join(f'{s}({c})' for s,c,_,_ in winners)}")
    print("→ These earn a PROPER fine-grained + walk-forward test before trusting.")
else:
    print("\nNothing clears the screen — concept doesn't obviously travel either.")
print("\n(Screen only: 2yr/hourly. Survivors aren't validated — they're candidates.)")
