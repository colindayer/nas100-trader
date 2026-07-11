"""PART A: existing S1 (Asian sweep) + S5 (ORB) definitions, UNCHANGED, across an
11-ticker liquid universe. Alpaca extended-hours hourly, 2021+ (same lineage as the
originally-validated 9-ticker basket). No per-ticker tuning. 3 bps/side.
Output: research/results/universe_expansion.md
"""
import os, sys, warnings
import numpy as np, pandas as pd, pytz
warnings.filterwarnings("ignore")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
eastern = pytz.timezone("US/Eastern")
SLIP = 0.0003
UNIV = ["QQQ", "SPY", "IWM", "DIA", "SMH", "SOXX", "XLK", "XLF", "XLE", "GLD", "TLT"]
CFD_MAP = {"QQQ": "US100", "SPY": "US500", "GLD": "XAUUSD", "DIA": "US30",
           "IWM": "US2000(?)"}  # rest have NO Pepperstone CFD -> Alpaca-only

from datetime import datetime
import pytz as tz
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from broker import load_config
cfg = load_config("alpaca")
cl = StockHistoricalDataClient(cfg["key"].strip(), cfg["secret"].strip())
print("fetching 11 tickers hourly 2021+ (batched)...")
req = StockBarsRequest(symbol_or_symbols=UNIV, timeframe=TimeFrame.Hour,
                       start=datetime(2021, 1, 1, tzinfo=tz.utc))
raw = cl.get_stock_bars(req).df

def prep(sym):
    d = raw.xs(sym, level="symbol").copy()
    d.index = pd.to_datetime(d.index.get_level_values(-1) if isinstance(d.index, pd.MultiIndex) else d.index, utc=True).tz_convert(eastern)
    d = d[["open", "high", "low", "close", "volume"]]
    d.columns = ["Open", "High", "Low", "Close", "Volume"]
    d["Date"] = d.index.date
    return d

def features(q):
    q = q.copy()
    q["SD"] = q.index.map(lambda i: (i + pd.Timedelta(days=1)).date() if i.hour >= 18 else i.date())
    ab = q[q.index.map(lambda i: i.hour >= 18 or i.hour < 2)]
    q["AL"] = q["SD"].map(ab.groupby("SD")["Low"].min())
    q["InS"] = q.index.map(lambda x: (2 <= x.hour < 5) or (9 <= x.hour < 12))
    tp = (q["High"] + q["Low"] + q["Close"]) / 3
    vv, ct, cv, p_ = [], 0.0, 0.0, None
    for i in range(len(q)):
        d = q["Date"].iloc[i]
        if d != p_: ct = cv = 0.0; p_ = d
        vol = q["Volume"].iloc[i]
        if vol > 0: ct += tp.iloc[i] * vol; cv += vol
        vv.append(ct / cv if cv > 0 else np.nan)
    q["VWAP"] = vv
    dc = q[q.index.hour == 16][["Close"]].copy(); dc.index = dc.index.date
    dc = dc[~dc.index.duplicated(keep="last")]
    q["EMA50"] = q["Date"].map(dc["Close"].ewm(span=50).mean().to_dict())
    pc = q["Close"].shift(1)
    tr = pd.concat([q["High"]-q["Low"], (q["High"]-pc).abs(), (q["Low"]-pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean(); q["HV"] = atr > 1.5 * atr.rolling(200).mean()
    q["S1"] = ((q["Low"] < q["AL"]) & (q["Close"] > q["AL"]) & q["InS"] & (q["Close"] > q["VWAP"])
               & (q["Close"] > q["EMA50"]) & ~q["HV"] & q["AL"].notna()).astype(int)
    orb = q[q.index.hour == 9]
    q["OH"] = q["Date"].map({d: h for d, h in zip(orb["Date"], orb["High"])})
    q["OV"] = q["Date"].map({d: v for d, v in zip(orb["Date"], orb["Volume"])})
    q["S5"] = (q.index.map(lambda x: 10 <= x.hour <= 13) & (q["Close"] > q["OH"])
               & q["OH"].notna() & (q["Volume"] > q["OV"] * 0.6)).astype(int)
    return q

def run(q, col, risk, sl, rr):
    cap = 10_000.0; in_t = False; entry = stop = tgt = sh = 0.0
    day_traded = None; trades = 0; daily_eq = {}
    sig = q[col].values; close = q["Close"].values; dates = q["Date"].values
    for i in range(1, len(q)):
        price = close[i]; d = dates[i]
        if in_t:
            if price <= stop: cap += sh*(stop-entry) - sh*(entry+stop)*SLIP; in_t = False
            elif price >= tgt: cap += sh*(tgt-entry) - sh*(entry+tgt)*SLIP; in_t = False
        elif sig[i-1] == 1 and day_traded != d:
            in_t = True; day_traded = d; entry = price; trades += 1
            stop = price*(1-sl); tgt = price*(1+sl*rr)
            sh = (cap*risk)/(price*sl)
        daily_eq[d] = cap
    eq = pd.Series(daily_eq).sort_index(); ret = eq.pct_change().dropna()
    yrs = max(len(eq)/252, 1e-9)
    half = len(ret)//2
    def shp(x): return x.mean()/x.std()*np.sqrt(252) if len(x) > 20 and x.std() > 0 else np.nan
    # yearly to detect period concentration
    e2 = eq.copy(); e2.index = pd.to_datetime(e2.index)
    yearly = e2.resample("YE").last().pct_change().dropna()
    conc = (yearly.max() / max(eq.iloc[-1]/eq.iloc[0]-1, 1e-9)) if eq.iloc[-1] > eq.iloc[0] else np.nan
    return {"ret": ret, "trades": trades, "CAGR": (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1,
            "Sharpe": shp(ret), "IS": shp(ret.iloc[:half]), "OOS": shp(ret.iloc[half:]),
            "MaxDD": (eq/eq.cummax()-1).min(), "best_yr_share": conc}

S = {"S1": (0.007, 0.015, 3.0), "S5": (0.0075, 0.010, 3.0)}
streams = {}; rows = []
for sym in UNIV:
    try:
        q = features(prep(sym))
    except Exception as e:
        rows.append((sym, "-", f"data error: {e}", None)); continue
    for sname, (risk, sl, rr) in S.items():
        r = run(q, sname, risk, sl, rr)
        streams[f"{sname}_{sym}"] = r["ret"]
        rows.append((sym, sname, "", r))

# correlation of return streams vs the QQQ mothership
corr_notes = []
qq = {"S1": streams.get("S1_QQQ"), "S5": streams.get("S5_QQQ")}
for k, v in streams.items():
    sname, sym = k.split("_")
    if sym == "QQQ": continue
    base = qq[sname]
    j = pd.DataFrame({"a": v, "b": base}).dropna()
    c = j["a"].corr(j["b"]) if len(j) > 50 else np.nan
    corr_notes.append((k, c))

out = ["# PART A — Universe expansion (S1 + S5 unchanged, 11 tickers, 2021+)",
       "\n_Alpaca extended-hours hourly (same lineage as the validated basket). "
       "3 bps/side. No per-ticker tuning. IS/OOS = first/second half. "
       "best_yr_share = best year's P&L / total (concentration flag >0.8)._\n",
       "| ticker | strat | CAGR | Sharpe | IS | OOS | MaxDD | trades | bestYr share | corr to QQQ-twin | CFD? | verdict |",
       "|---|---|---|---|---|---|---|---|---|---|---|---|"]
cd = dict(corr_notes)
keep = []
for sym, sname, err, r in rows:
    if err:
        out.append(f"| {sym} | {sname} | {err} | | | | | | | | | REJECT |"); continue
    c = cd.get(f"{sname}_{sym}", 1.0)
    cfd = CFD_MAP.get(sym, "none")
    ok = (not np.isnan(r["OOS"]) and r["OOS"] > 0.4 and r["IS"] > 0 and r["trades"] >= 40
          and (np.isnan(r["best_yr_share"]) or r["best_yr_share"] < 0.8))
    indep = (np.isnan(c) or c < 0.5)
    verdict = ("KEEP" if ok and (sym == "QQQ" or indep) else
               ("DUPLICATE (corr)" if ok else "REJECT (economics)"))
    if verdict == "KEEP": keep.append(f"{sname}_{sym}")
    cs = "" if np.isnan(c) or sym == "QQQ" else f"{c:.2f}"
    out.append(f"| {sym} | {sname} | {r['CAGR']:+.1%} | {r['Sharpe']:.2f} | {r['IS']:.2f} | "
               f"{r['OOS']:.2f} | {r['MaxDD']:.1%} | {r['trades']} | "
               f"{'' if np.isnan(r['best_yr_share']) else f'{r["best_yr_share"]:.0%}'} | {cs} | {cfd} | {verdict} |")

# pooled portfolio of keepers (equal weight daily)
if keep:
    pool = pd.DataFrame({k: streams[k] for k in keep}).fillna(0).mean(axis=1)
    shp = pool.mean()/pool.std()*np.sqrt(252)
    out.append(f"\n**Pooled (keepers, equal weight): Sharpe {shp:.2f}, {len(keep)} streams: {keep}**")
avg_corr = np.nanmean([c for _, c in corr_notes])
out.append(f"\nMean correlation of non-QQQ streams to their QQQ twin: **{avg_corr:.2f}** — "
           "values near/above 0.5 = mostly duplicated Nasdaq exposure, not independent opportunity.")
path = os.path.join(REPO, "research", "results", "universe_expansion.md")
open(path, "w").write("\n".join(out) + "\n")
print("\n".join(out))
