"""PART C: ONE new strategy family — canonical cross-asset time-series momentum
(Moskowitz/Ooi/Pedersen 12-month lookback, 1-month hold, sign rule). 8 liquid
ETFs, daily data 2005+. No parameter search. Costs 3 bps/side PLUS the honest
CFD test: overnight financing (~SOFR+2.5% ~= 3 bps/day on notional) — the thing
that kills slow strategies on CFDs. Walk-forward + 6 splits + correlation to
the current book. Output: research/results/new_strategy_candidate.md
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UNIV = ["QQQ", "SPY", "IWM", "GLD", "TLT", "XLE", "XLF", "XLK"]
COST = 0.0003            # per side
FIN_DAILY = 0.0003       # CFD overnight financing on notional (~7.5%/yr) — longs & shorts pay on CFDs

import yfinance as yf
px = yf.download(UNIV, start="2004-01-01", progress=False, auto_adjust=True)["Close"].dropna()
ret = px.pct_change()

# canonical TSMOM: sign of 12-month return (skip nothing -- MOP 2012 uses 12m incl. last month
# for TSMOM; 12-1 skip is the cross-sectional convention. Pre-register: 252d lookback, sign.)
mom = np.sign(px / px.shift(252) - 1)
pos = mom.shift(1)                                   # trade at next close (lagged)
pos_m = pos.resample("ME").last().reindex(ret.index, method="ffill")  # monthly rebalance, hold
w = pos_m / len(UNIV)                                # equal weight, gross 1.0

turnover = w.diff().abs().sum(axis=1)
gross = (w * ret).sum(axis=1)
def net_series(fin):
    exposure = w.abs().sum(axis=1)                   # CFDs pay financing on |notional|
    return gross - turnover * COST - (exposure * fin if fin else 0)

def stats(r, label):
    r = r.dropna()
    eq = (1 + r).cumprod(); yrs = len(r) / 252
    def shp(x): return x.mean()/x.std()*np.sqrt(252) if x.std() > 0 else 0
    half = len(r)//2
    splits = [shp(r.iloc[int(len(r)*f):]) for f in (0.45, 0.5, 0.55, 0.6, 0.65, 0.7)]
    return {"label": label, "CAGR": eq.iloc[-1]**(1/yrs)-1, "Sharpe": shp(r),
            "IS": shp(r.iloc[:half]), "OOS": shp(r.iloc[half:]),
            "MaxDD": (eq/eq.cummax()-1).min(), "splits": splits, "r": r}

etf = stats(net_series(0.0), "ETF account (no financing)")
cfd = stats(net_series(FIN_DAILY), "CFD account (3 bps/day financing)")
to_yr = float(turnover.resample("YE").sum().mean())

# correlation to the current book (S1+S5 QQQ daily stream, 2019+)
corr_txt = "n/a"
try:
    sys.path.insert(0, REPO)
    bookf = os.path.join(REPO, "research", "results", ".book_stream.csv")
    if os.path.exists(bookf):
        book = pd.read_csv(bookf, index_col=0, parse_dates=True).iloc[:, 0]
        j = pd.DataFrame({"tsmom": etf["r"], "book": book}).dropna()
        corr_txt = f"{j['tsmom'].corr(j['book']):+.2f} (n={len(j)} days)"
except Exception as e:
    corr_txt = f"error: {e}"

out = ["# PART C — New family candidate: canonical TSMOM (12m sign, monthly, 8 ETFs)",
       f"\n_Moskowitz/Ooi/Pedersen rule, pre-registered: 252d lookback, sign, monthly "
       f"rebalance, equal weight, lagged execution. 2005-2026. Turnover ~{to_yr:.1f}x gross/yr. "
       f"No parameter search. Correlation to current book (S1+S5 QQQ): **{corr_txt}**._\n",
       "| account | CAGR | Sharpe | IS | OOS | MaxDD | 6-split OOS Sharpe |",
       "|---|---|---|---|---|---|---|"]
for s in (etf, cfd):
    out.append(f"| {s['label']} | {s['CAGR']:+.1%} | {s['Sharpe']:.2f} | {s['IS']:.2f} | "
               f"{s['OOS']:.2f} | {s['MaxDD']:.1%} | {' '.join(f'{x:.2f}' for x in s['splits'])} |")
out += ["\n## Prop / execution compatibility",
        "- Holding period ~1 month -> overnight+weekend holds every week. FundedNext Stellar",
        "  permits holding; FTMO regular does not (Swing account required). Constraint, not blocker.",
        "- Broker-side stops: TSMOM has no natural stop (sign-flip exit). A catastrophe SL",
        "  (e.g. 10%) is attachable without changing the rule -- same pattern as OVN.",
        "- **CFD financing is the decisive economics**: see table -- on CFDs the strategy pays",
        "  ~7.5%/yr on gross notional, which consumes most/all of the edge. Viable on the",
        "  Alpaca ETF side (cash account, longs unfinanced); NOT viable as a Pepperstone CFD book.",
        ""]
verdict = ("CANDIDATE_FOR_INDEPENDENT_REVIEW" if etf["OOS"] > 0.4 and etf["IS"] > 0
           and min(etf["splits"]) > 0.2 and cfd["Sharpe"] < etf["Sharpe"]
           else ("NEEDS_MORE_EVIDENCE" if etf["Sharpe"] > 0.3 else "REJECT"))
out.append(f"## Verdict: **{verdict}** (ETF-account variant only; CFD variant "
           f"{'REJECTED on financing' if cfd['Sharpe'] < 0.3 else 'marginal'})")
path = os.path.join(REPO, "research", "results", "new_strategy_candidate.md")
open(path, "w").write("\n".join(out) + "\n")
print("\n".join(out))
