"""PART B: a-priori macro regime segmentation of the existing book's return
streams (S1+S5 on QQQ, 2019-2026, the validated engines). DESCRIPTIVE only —
no threshold search; canonical/pre-registered rules; all variables LAGGED one
day (information available at decision time). Verdict requires incremental
value over the existing VIX gates AND enough independent episodes.
Output: research/results/macro_regime_segmentation.md
"""
import io, os, sys, urllib.request, warnings
import numpy as np, pandas as pd, pytz
warnings.filterwarnings("ignore")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
eastern = pytz.timezone("US/Eastern")
SLIP = 0.0003

# ---- book return streams: S1 + S5 on QQQ (same engine as prior experiments) ----
df = pd.read_csv(os.path.join(REPO, "qqq_hourly_7y.csv"))
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
q = df[df["symbol"] == "QQQ"].set_index("timestamp").tz_convert(eastern)[
    ["open", "high", "low", "close", "volume"]]
q.columns = ["Open", "High", "Low", "Close", "Volume"]
try:
    from alpaca_broker import AlpacaBroker
    fresh = AlpacaBroker().get_bars("QQQ", "1Hour", 1200)
    q = pd.concat([q, fresh[fresh.index > q.index.max()]])
except Exception:
    pass
q["Date"] = q.index.date
q["SD"] = q.index.map(lambda i: (i + pd.Timedelta(days=1)).date() if i.hour >= 18 else i.date())
ab = q[q.index.map(lambda i: i.hour >= 18 or i.hour < 2)]
q["AL"] = q["SD"].map(ab.groupby("SD")["Low"].min())
q["InS"] = q.index.map(lambda x: (2 <= x.hour < 5) or (9 <= x.hour < 12))
tp = (q["High"]+q["Low"]+q["Close"])/3
vv, ct, cv, p_ = [], 0.0, 0.0, None
for i in range(len(q)):
    d = q["Date"].iloc[i]
    if d != p_: ct = cv = 0.0; p_ = d
    v = q["Volume"].iloc[i]
    if v > 0: ct += tp.iloc[i]*v; cv += v
    vv.append(ct/cv if cv > 0 else np.nan)
q["VWAP"] = vv
dc = q[q.index.hour == 16][["Close"]].copy(); dc.index = dc.index.date
dc = dc[~dc.index.duplicated(keep="last")]
q["EMA50"] = q["Date"].map(dc["Close"].ewm(span=50).mean().to_dict())
pc = q["Close"].shift(1)
tr = pd.concat([q["High"]-q["Low"], (q["High"]-pc).abs(), (q["Low"]-pc).abs()], axis=1).max(axis=1)
atr = tr.rolling(14).mean(); q["HV"] = atr > 1.5*atr.rolling(200).mean()
q["S1"] = ((q["Low"] < q["AL"]) & (q["Close"] > q["AL"]) & q["InS"] & (q["Close"] > q["VWAP"])
           & (q["Close"] > q["EMA50"]) & ~q["HV"] & q["AL"].notna()).astype(int)
orb = q[q.index.hour == 9]
q["OH"] = q["Date"].map({d: h for d, h in zip(orb["Date"], orb["High"])})
q["OV"] = q["Date"].map({d: v for d, v in zip(orb["Date"], orb["Volume"])})
q["S5"] = (q.index.map(lambda x: 10 <= x.hour <= 13) & (q["Close"] > q["OH"])
           & q["OH"].notna() & (q["Volume"] > q["OV"]*0.6)).astype(int)

def run(col, risk, sl, rr):
    cap = 10_000.0; in_t = False; entry = stop = tgt = sh = 0.0
    day_traded = None; daily_eq = {}
    sig = q[col].values; close = q["Close"].values; dates = q["Date"].values
    for i in range(1, len(q)):
        price = close[i]; d = dates[i]
        if in_t:
            if price <= stop: cap += sh*(stop-entry)-sh*(entry+stop)*SLIP; in_t = False
            elif price >= tgt: cap += sh*(tgt-entry)-sh*(entry+tgt)*SLIP; in_t = False
        elif sig[i-1] == 1 and day_traded != d:
            in_t = True; day_traded = d; entry = price
            stop = price*(1-sl); tgt = price*(1+sl*rr); sh = (cap*risk)/(price*sl)
        daily_eq[d] = cap
    eq = pd.Series(daily_eq).sort_index()
    return eq.pct_change().dropna()

book = (run("S1", 0.007, 0.015, 3.0) + run("S5", 0.0075, 0.010, 3.0)).dropna()
book.index = pd.to_datetime(book.index)

# ---- regime variables (FRED csv + yfinance), all LAGGED 1 day ----
def fred(sid):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    r = urllib.request.urlopen(url, timeout=30).read()
    s = pd.read_csv(io.BytesIO(r))
    s.columns = ["date", "v"]
    s["v"] = pd.to_numeric(s["v"], errors="coerce")
    s["date"] = pd.to_datetime(s["date"])
    return s.set_index("date")["v"].dropna()

import yfinance as yf
def yfd(t):
    s = yf.download(t, start="2018-01-01", progress=False)["Close"]
    if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s

vix = yfd("^VIX"); vix3m = yfd("^VIX3M"); dxy = yfd("DX-Y.NYB")
dgs2, dgs10 = fred("DGS2"), fred("DGS10")
hy = fred("BAMLH0A0HYM2")
walcl, tga, rrp = fred("WALCL"), fred("WTREGEN"), fred("RRPONTSYD")
netliq = (walcl - tga.reindex(walcl.index, method="ffill")
          - rrp.reindex(walcl.index, method="ffill")).dropna()

# canonical / pre-registered rules (risk-ON condition), all evaluated LAGGED:
REGIMES = {
    "VIX21ma<20 (existing gate)":       (vix.rolling(21).mean() < 20),
    "VIX3M/VIX>1 (validated shadow)":   ((vix3m/vix) > 1.0),
    "DGS2 falling (63d chg<0)":         (dgs2.diff(63) < 0),
    "DGS10 falling (63d chg<0)":        (dgs10.diff(63) < 0),
    "curve 10y-2y>0":                   ((dgs10-dgs2) > 0),
    "HY OAS < 200d MA":                 (hy < hy.rolling(200).mean()),
    "DXY < 200d MA":                    (dxy < dxy.rolling(200).mean()),
    "netliq rising (13w chg>0)":        (netliq.diff(13) > 0),
}
# breadth: pre-registered rejection — no survivorship-safe free constituent data.

def episodes(b):
    return int((b.astype(int).diff() == 1).sum()) + int(b.iloc[0])

base_sharpe = book.mean()/book.std()*np.sqrt(252)
out = ["# PART B — Macro regime segmentation (descriptive, lagged, canonical rules)",
       f"\n_Book = S1+S5 on QQQ 2019-2026 (validated engines, 3 bps). Whole-sample "
       f"Sharpe {base_sharpe:.2f}. Every variable lagged 1 day. No threshold search. "
       f"Breadth: pre-registered REJECT (no survivorship-safe free data)._\n",
       "| regime (risk-ON rule) | %days ON | Sharpe ON | Sharpe OFF | episodes | verdict |",
       "|---|---|---|---|---|---|"]
for name, b in REGIMES.items():
    b = b.dropna().shift(1).dropna()               # LAG: yesterday's value
    b = b.reindex(book.index, method="ffill").dropna()
    r = book.reindex(b.index)
    on, off = r[b.astype(bool)], r[~b.astype(bool)]
    def shp(x): return x.mean()/x.std()*np.sqrt(252) if len(x) > 40 and x.std() > 0 else np.nan
    ep = episodes(b.astype(bool))
    so, sf = shp(on), shp(off)
    if ep < 8:
        v = "REJECT (too few episodes)"
    elif np.isnan(sf) or np.isnan(so):
        v = "REJECT (insufficient off-sample)"
    elif "existing" in name:
        v = "baseline reference"
    elif "validated shadow" in name:
        v = "CANDIDATE (already under forward shadow)"
    elif so - sf > 0.5 and so > base_sharpe + 0.1:
        v = "NEEDS_MORE_EVIDENCE (segmentation only)"
    else:
        v = "REJECT (no incremental value)"
    out.append(f"| {name} | {b.mean():.0%} | {so:.2f} | {sf:.2f} | {ep} | {v} |")
out.append("\nRule applied: a variable must (a) have >=8 independent episodes, "
           "(b) separate ON/OFF Sharpe by >0.5, (c) beat the whole-sample Sharpe when ON "
           "— and even then it is only NEEDS_MORE_EVIDENCE until tested as a gate with "
           "incremental value over the existing VIX gates (the EXP-20260711-01 protocol).")
path = os.path.join(REPO, "research", "results", "macro_regime_segmentation.md")
open(path, "w").write("\n".join(out) + "\n")
print("\n".join(out))
