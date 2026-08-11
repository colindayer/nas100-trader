"""TASK 2 + 3 — BREADTH PANEL and the BREADTH TEST.

    python scripts/breadth_panel.py

THE HYPOTHESIS IS DIVERSIFICATION, NOT SYMBOL SELECTION.
  Universes below are declared by ASSET CLASS AVAILABILITY, never by historical performance.
  No instrument is included because it performed well. That distinction is the whole experiment:
  if we picked instruments by past Sharpe we would reproduce the RAAM failure, where a ranking
  lost to random ranking through identical machinery.

WHAT IS FROZEN (all of it — nothing here is tuned)
  signal        sign(close.pct_change(252)).shift(1)      the production TREND signal
  weighting     inverse-vol, normalised, then scaled to a volatility target
  band          0.005 no-trade band per symbol
  costs         3 bps per side on turnover
  target vol    5%, max leverage 3.0
  Only the UNIVERSE changes.

SCOPE, STATED PLAINLY
  This runs on the 13-instrument daily panel we already own (2000-2026): 7 FX, 4 commodities,
  2 equity indices. It contains NO BONDS, which is the single largest diversification gap
  identified in DATA_ROADMAP.md and cannot be closed until FTMO_UNIVERSE.csv exists. So this
  measures 6 -> 13, not the 6 -> 30 that the roadmap proposes. A null here would NOT refute
  breadth; it would bound what breadth is worth WITHOUT new asset classes.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exp_turnover import COST_BPS, WARMUP, held_band
from scripts.exp_mechanism import weight_path_lb
from scripts.candidate_v2_regime import ftmo_sweep

OUT = ROOT / "backtest_out" / "breadth"
PANEL = ROOT / "data" / "reference" / "portfolio_D1.csv"
ANN, BAND, LOOKBACK, MAX_LEV, TARGET_VOL = 252, 0.005, 252, 3.0, 0.05

ASSET_CLASS = {
    "EURUSD": "FX", "GBPUSD": "FX", "USDJPY": "FX", "AUDUSD": "FX",
    "USDCAD": "FX", "USDCHF": "FX", "NZDUSD": "FX",
    "GOLD": "METAL", "SILVER": "METAL",
    "OIL": "ENERGY", "COPPER": "METAL_IND",
    "NAS100": "INDEX", "SP500": "INDEX",
}

# PREDECLARED universes. Membership is by ASSET CLASS, never by performance.
UNIVERSES = {
    "U1_incumbent_6":      ["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500"],
    "U2_index_only":       ["NAS100", "SP500"],
    "U3_commodity_only":   ["GOLD", "SILVER", "OIL", "COPPER"],
    "U4_fx_only":          ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"],
    "U5_incumbent_plus_fx_majors": ["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500",
                                    "EURUSD", "GBPUSD", "USDJPY"],
    "U6_all_13":           list(ASSET_CLASS.keys()),
}

DISCOVERY = ("2000-01-01", "2012-12-31")
VALIDATION = ("2013-01-01", "2026-12-31")


# ---------------------------------------------------------------- panel + quality
def build_panel():
    d = pd.read_csv(PANEL, index_col=0, parse_dates=True).sort_index()
    syms = sorted({c.rsplit("_", 1)[0] for c in d.columns})
    cl = d[[f"{s}_close" for s in syms]].copy()
    cl.columns = syms
    quality = []
    for s in syms:
        raw = cl[s]
        first = raw.first_valid_index()
        seg = raw.loc[first:]
        n_missing = int(seg.isna().sum())
        rets = seg.ffill().pct_change()
        zero_runs = int((rets == 0).sum())
        quality.append({
            "symbol": s, "asset_class": ASSET_CLASS.get(s, "UNKNOWN"),
            "first_date": str(first.date()), "last_date": str(raw.last_valid_index().date()),
            "bars": int(seg.notna().sum()), "missing_after_start": n_missing,
            "pct_missing": round(100 * n_missing / max(len(seg), 1), 3),
            "zero_return_bars": zero_runs,
            "pct_zero_returns": round(100 * zero_runs / max(len(rets), 1), 3),
            "ann_vol": round(float(rets.std() * np.sqrt(ANN)), 4),
            "quality": ("HIGH" if n_missing / max(len(seg), 1) < 0.005 and
                        zero_runs / max(len(rets), 1) < 0.05 else "MEDIUM"),
        })
    return cl.ffill(), pd.DataFrame(quality)


def panel_hash(cl: pd.DataFrame) -> str:
    b = pd.util.hash_pandas_object(cl.round(8), index=True).values.tobytes()
    return hashlib.sha256(b).hexdigest()[:16]


# ---------------------------------------------------------------- engine (frozen)
def net_returns(px: pd.DataFrame):
    P = weight_path_lb(px, TARGET_VOL, MAX_LEV, LOOKBACK)
    W = held_band(P, BAND).iloc[WARMUP:]
    r = px.pct_change().fillna(0.0).loc[W.index]
    turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
    gross = (W * r).sum(axis=1)
    net = gross - turn * COST_BPS / 1e4
    return net.dropna(), gross.dropna(), turn, W, r


def effective_bets(W: pd.DataFrame, r: pd.DataFrame) -> tuple:
    """ENB via the entropy of the PCA eigenvalue spectrum of the risk-weighted covariance,
    and correlation concentration as the top eigenvalue's share of total variance."""
    common = W.index.intersection(r.index)
    contrib = (W.loc[common] * r.loc[common]).dropna(how="all")
    contrib = contrib.loc[:, contrib.std() > 0]
    if contrib.shape[1] < 2:
        return 1.0, 1.0
    cov = contrib.cov().to_numpy()
    ev = np.linalg.eigvalsh(cov)
    ev = ev[ev > 0]
    if len(ev) == 0:
        return 1.0, 1.0
    p = ev / ev.sum()
    enb = float(np.exp(-(p * np.log(p)).sum()))
    top = float(p.max())
    return enb, top


def stats(net, gross, turn, W, r, label):
    eq = (1 + net).cumprod()
    yrs = len(net) / ANN
    dd = float((eq / eq.cummax() - 1).min())
    enb, top = effective_bets(W, r)
    return {
        "universe": label, "n_assets": W.shape[1],
        "CAGR": eq.iloc[-1] ** (1 / yrs) - 1,
        "vol": float(net.std() * np.sqrt(ANN)),
        "sharpe_net": float(net.mean() / net.std() * np.sqrt(ANN)),
        "sharpe_gross": float(gross.mean() / gross.std() * np.sqrt(ANN)),
        "maxDD": dd,
        "turnover_per_day": float(turn.mean()),
        "annual_cost": float(turn.mean() * ANN * COST_BPS / 1e4),
        "effective_bets": enb,
        "top_eigen_share": top,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cl, qual = build_panel()
    h = panel_hash(cl)
    qual.to_csv(OUT / "BREADTH_PANEL_QUALITY.csv", index=False)
    cl.to_csv(OUT / "BREADTH_PANEL.csv")
    json.dump({"panel_hash": h, "n_symbols": cl.shape[1], "rows": len(cl),
               "start": str(cl.index[0].date()), "end": str(cl.index[-1].date()),
               "universes": UNIVERSES, "note": "NO BONDS — see DATA_ROADMAP.md"},
              open(OUT / "BREADTH_PANEL_META.json", "w"), indent=1)

    print("=" * 108)
    print(f" BREADTH PANEL   hash {h}   {cl.shape[1]} symbols   "
          f"{cl.index[0].date()} .. {cl.index[-1].date()}")
    print(" NO BONDS in this panel — the largest diversification gap remains unclosed")
    print("=" * 108)
    print(f"  {'symbol':<9}{'class':<11}{'first':<12}{'bars':>7}{'%miss':>8}"
          f"{'%zero':>8}{'annvol':>9}{'quality':>9}")
    for _, q in qual.iterrows():
        print(f"  {q['symbol']:<9}{q['asset_class']:<11}{q['first_date']:<12}{q['bars']:>7}"
              f"{q['pct_missing']:>8.2f}{q['pct_zero_returns']:>8.2f}{q['ann_vol']:>9.3f}"
              f"{q['quality']:>9}")

    # ---------------- full sample
    print("\n" + "=" * 108)
    print(" BREADTH COMPARISON — universes declared by ASSET CLASS, not by performance")
    print("=" * 108)
    rows, series = [], {}
    print(f"  {'universe':<30}{'n':>4}{'CAGR':>8}{'vol':>7}{'ShNet':>7}{'ShGr':>7}"
          f"{'maxDD':>8}{'turn/d':>8}{'cost/yr':>9}{'ENB':>6}{'top-eig':>9}")
    for name, syms in UNIVERSES.items():
        px = cl[syms].dropna()
        net, gross, turn, W, r = net_returns(px)
        s = stats(net, gross, turn, W, r, name)
        rows.append(s); series[name] = net
        print(f"  {name:<30}{s['n_assets']:>4}{s['CAGR']:>8.2%}{s['vol']:>7.2%}"
              f"{s['sharpe_net']:>7.2f}{s['sharpe_gross']:>7.2f}{s['maxDD']:>8.1%}"
              f"{s['turnover_per_day']:>8.4f}{s['annual_cost']:>9.2%}"
              f"{s['effective_bets']:>6.2f}{s['top_eigen_share']:>9.1%}")

    # ---------------- nested chronological folds
    print("\n" + "=" * 108)
    print(" NESTED CHRONOLOGICAL VALIDATION — same predeclared universes, both segments")
    print("=" * 108)
    print(f"  {'universe':<30}{'disc Sharpe':>13}{'val Sharpe':>12}{'disc DD':>10}"
          f"{'val DD':>9}{'both>U1?':>10}")
    base_d = base_v = None
    fold_rows = []
    for name, syms in UNIVERSES.items():
        px = cl[syms].dropna()
        net, _, _, _, _ = net_returns(px)
        d = net.loc[DISCOVERY[0]:DISCOVERY[1]]
        v = net.loc[VALIDATION[0]:VALIDATION[1]]
        sd = float(d.mean() / d.std() * np.sqrt(ANN))
        sv = float(v.mean() / v.std() * np.sqrt(ANN))
        ddd = float(((1 + d).cumprod() / (1 + d).cumprod().cummax() - 1).min())
        ddv = float(((1 + v).cumprod() / (1 + v).cumprod().cummax() - 1).min())
        if name == "U1_incumbent_6":
            base_d, base_v = sd, sv
        better = (sd > base_d and sv > base_v) if base_d is not None else False
        fold_rows.append({"universe": name, "disc_sharpe": sd, "val_sharpe": sv,
                          "disc_dd": ddd, "val_dd": ddv, "beats_incumbent_both": better})
        print(f"  {name:<30}{sd:>13.2f}{sv:>12.2f}{ddd:>10.1%}{ddv:>9.1%}"
              f"{('YES' if better else '-'):>10}")

    # ---------------- asset-class contribution for the widest universe
    print("\n" + "=" * 108)
    print(" ASSET-CLASS CONTRIBUTION (U6_all_13) — is any improvement from ONE asset?")
    print("=" * 108)
    px = cl[UNIVERSES["U6_all_13"]].dropna()
    net, gross, turn, W, r = net_returns(px)
    common = W.index.intersection(r.index)
    contrib = (W.loc[common] * r.loc[common])
    tot = contrib.sum().sum()
    print(f"  {'symbol':<9}{'class':<11}{'ann ret':>10}{'share of P&L':>15}{'risk share':>12}")
    var_tot = contrib.sum(axis=1).var()
    for s in sorted(contrib.columns, key=lambda x: -contrib[x].sum()):
        rs = float(contrib[s].cov(contrib.sum(axis=1)) / var_tot) if var_tot > 0 else np.nan
        print(f"  {s:<9}{ASSET_CLASS.get(s,'?'):<11}{contrib[s].mean()*ANN:>+10.2%}"
              f"{contrib[s].sum()/tot:>15.1%}{rs:>12.1%}")

    # ---------------- FTMO under time limits
    print("\n" + "=" * 108)
    print(" FTMO PHASE 1 UNDER TIME LIMITS")
    print("=" * 108)
    for cap in (60, 90, 180, 365):
        print(f"\n   --- {cap}d limit")
        print(f"  {'universe':<30}{'pass%':>9}{'breach%':>10}{'timeout%':>10}{'med days':>10}")
        for name in UNIVERSES:
            s = ftmo_sweep(series[name], cap)
            if s:
                print(f"  {name:<30}{s['pass_%']:>9.1f}{s['breach_%']:>10.1f}"
                      f"{s['timeout_%']:>10.1f}{(s['median_days'] or 0):>10.0f}")

    pd.DataFrame(rows).to_csv(OUT / "breadth_comparison.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(OUT / "breadth_folds.csv", index=False)

    # ponytail: the only silent killer here is a universe that quietly loses history to dropna
    for name, syms in UNIVERSES.items():
        n_rows = len(cl[syms].dropna())
        assert n_rows > 3000, f"{name} retains only {n_rows} rows after dropna — history loss"
    print(f"\n  self-check OK: every universe retains >3000 rows after alignment")
    print(f"  written -> {OUT}/")


if __name__ == "__main__":
    main()
