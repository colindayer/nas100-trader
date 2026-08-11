"""Experiments 5-6 against CANDIDATE V2 + band 0.005: vol target, then trend lookback.

    python scripts/exp_mechanism.py

CURRENT CANDIDATE (unfrozen): TREND-only, GOLD SILVER OIL COPPER NAS100 SP500, no-trade band 0.005
    Sharpe 0.663  maxDD -15.87%  CAGR ~5.3%  cost 0.301%/yr  turn 0.0398
    train 0.564 / oos 0.577

5 VOLATILITY TARGET
   target_vol is a pure scaling of the book, so Sharpe is close to invariant BY CONSTRUCTION --
   the interesting effects are second-order: where max_leverage clips (the scale is capped at 3.0,
   so a high target stops scaling and the realised vol falls short), and how cost drag scales
   against return. The practical prize is drawdown: -15.87% misses the <15% milestone by 0.87pp,
   and a lower target is the only lever that moves drawdown without touching the signal.

6 TREND LOOKBACK
   This is the ONLY experiment here that changes the signal. Production hard-codes
   pct_change(252). Parity with target_weights() therefore holds ONLY at 252, and the parity check
   below is run at 252 and asserted. If a different lookback wins, production must be changed and
   re-verified -- it does not become the baseline by winning a backtest.

   Predeclared grid, fixed before any result: 126, 189, 252, 378 (6m, 9m, 12m, 18m). Four values,
   one of which is the incumbent. 12-month TSMOM is the literature standard (Moskowitz/Ooi/
   Pedersen 2012), so the incumbent is a prior, not an arbitrary pick.

ACCEPTANCE (operator, strict priority): net Sharpe, max drawdown, annual costs, turnover, CAGR.
Eligible only if Sharpe improves and drawdown does not worsen by more than 1pp, AND out-of-sample
does not collapse relative to train.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exp_turnover import COST_BPS, DD_TOL, V2, WARMUP, held_band, stats
from scripts.greedy_universe import load_close, verify
from scripts.portfolio_mt5 import CONFIGS, _ivol, target_weights

OUT = ROOT / "backtest_out" / "mechanism"
BAND = 0.005

GRID_VOL = [0.04, 0.05, 0.06, 0.08, 0.10]       # 0.08 is the incumbent
GRID_LOOKBACK = [126, 189, 252, 378]            # 252 is the incumbent


def weight_path_lb(px, target_vol, max_leverage, lookback=252):
    """Identical to production target_weights (TREND-only) except the momentum lookback.
    At lookback=252 this is byte-identical -- asserted in main()."""
    ret = px.pct_change().fillna(0.0)
    tsig = np.sign(px.pct_change(lookback)).shift(1).fillna(0.0)
    tw = tsig * _ivol(ret)
    tw = tw.div(tw.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    port_ret = (tw.shift(1) * ret).sum(axis=1)
    realized = (port_ret.ewm(span=252).std() * np.sqrt(252)).clip(lower=1e-4)
    scale = (target_vol / realized).clip(0, max_leverage)
    return tw.mul(scale, axis=0)


def run_variant(px, target_vol, max_lev, lookback):
    P = weight_path_lb(px, target_vol, max_lev, lookback)
    return stats(held_band(P, BAND), px.pct_change().fillna(0.0))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    close = load_close()
    cfg = dict(CONFIGS["funded"]); cfg["sleeves"] = ("TREND",)

    # parity: the lookback-parameterised path must equal production at the incumbent 252
    err = verify(close, cfg)
    rng = np.random.default_rng(1)
    Pfull = weight_path_lb(close, cfg["target_vol"], cfg["max_leverage"], 252)
    worst = 0.0
    for i in rng.choice(range(400, len(close)), 12, replace=False):
        w, _ = target_weights(close.iloc[:i], carry_signs={}, **cfg)
        worst = max(worst, float((w.reindex(close.columns).fillna(0.0) - Pfull.iloc[i - 1]).abs().max()))
    print(f"parity at lookback=252 vs production: {worst:.3e}")
    if worst > 0:
        raise SystemExit("lookback-parameterised path is not identical to production at 252")

    px = close[V2].dropna(how="any")
    tr, oo = px.loc[:"2016-12-31"], px.loc["2017-01-01":]
    base = run_variant(px, 0.08, 3.0, 252)
    print(f"\nCANDIDATE: sharpe {base['sharpe']:.3f}  maxDD {base['maxdd']:.2%}  "
          f"CAGR {base['cagr']:.2%}  vol {base['vol']:.2%}  cost {base['cost_yr']:.3%}")

    rows = []

    def record(name, tv, lb):
        s = run_variant(px, tv, 3.0, lb)
        s_tr = run_variant(tr, tv, 3.0, lb)["sharpe"]
        s_oo = run_variant(oo, tv, 3.0, lb)["sharpe"]
        d_sh, d_dd = s["sharpe"] - base["sharpe"], s["maxdd"] - base["maxdd"]
        stable = s_oo >= s_tr - 0.15
        verdict = ("ACCEPT" if d_sh > 0 and d_dd >= -DD_TOL and stable else
                   "reject: OOS degrades" if d_sh > 0 and d_dd >= -DD_TOL else
                   "reject: no Sharpe gain" if d_sh <= 0 else "reject: drawdown")
        if abs(tv - 0.08) < 1e-9 and lb == 252:
            verdict = "(incumbent)"
        rows.append({"variant": name, "target_vol": tv, "lookback": lb, **s,
                     "d_sharpe": d_sh, "d_maxdd": d_dd,
                     "train_sharpe": s_tr, "oos_sharpe": s_oo, "verdict": verdict})
        print(f"  {name:<20}{s['sharpe']:8.3f}{d_sh:+8.3f}{s['maxdd']:9.2%}{d_dd:+8.2%}"
              f"{s['vol']:8.2%}{s['cost_yr']:8.3%}{s_tr:8.3f}{s_oo:8.3f}  {verdict}")

    hdr = (f"\n  {'variant':<20}{'sharpe':>8}{'d':>8}{'maxDD':>9}{'d':>8}{'vol':>8}"
           f"{'cost':>8}{'train':>8}{'oos':>8}  verdict")
    print("\n" + "=" * 96 + "\n 5  VOLATILITY TARGET  (signal untouched; pure scaling)\n" + "=" * 96 + hdr)
    for tv in GRID_VOL:
        record(f"vol_{tv:.2f}", tv, 252)

    print("\n" + "=" * 96 + "\n 6  TREND LOOKBACK  (CHANGES THE SIGNAL — production is 252)\n" + "=" * 96 + hdr)
    for lb in GRID_LOOKBACK:
        record(f"lookback_{lb}", 0.08, lb)

    R = pd.DataFrame(rows)
    acc = R[R["verdict"] == "ACCEPT"].sort_values(
        by=["sharpe", "maxdd", "cost_yr", "turnover_day", "cagr"],
        ascending=[False, False, True, True, False])
    print("\n" + "=" * 96)
    if len(acc):
        for _, w in acc.iterrows():
            print(f" ELIGIBLE: {w['variant']:<16} sharpe {w['sharpe']:.3f}  maxDD {w['maxdd']:.2%}  "
                  f"vol {w['vol']:.2%}  train {w['train_sharpe']:.3f} / oos {w['oos_sharpe']:.3f}")
        print(f"\n selection over {len(rows) - 1} non-incumbent variants — stated, not hidden.")
    else:
        print(" NO VARIANT ELIGIBLE — candidate stands unchanged.")
    print("=" * 96)

    R.to_csv(OUT / "mechanism_experiments.csv", index=False)
    json.dump({"candidate": base, "results": rows,
               "grids": {"target_vol": GRID_VOL, "lookback": GRID_LOOKBACK},
               "note": "lookback != 252 requires changing production target_weights and "
                       "re-verifying parity; winning a backtest does not make it the baseline"},
              open(OUT / "mechanism_experiments.json", "w"), indent=1)
    print(f"\n  written -> {OUT}")


if __name__ == "__main__":
    main()
