"""Greedy single-asset elimination against the LOCKED baseline.

    python scripts/greedy_universe.py

LOCKED BASELINE (frozen 2026-08-03, do not edit):
    code 4d0e06ad576c00be   data 9ff394f01bb02981
    Sharpe 0.363   CAGR 2.69%   vol 8.24%   maxDD -20.59%   costs 0.912%/yr

RULE (operator-specified): remove exactly one asset if and only if Sharpe increases AND drawdown
does not worsen materially. Freeze the new baseline. Repeat. Stop when no single removal improves
the portfolio. Nothing else changes -- not the vol target, not the lookback, not the rebalance
frequency, not the cost model.

SPEED, AND WHY IT IS STILL PARITY
---------------------------------
Every operation in the TREND sleeve is causal (pct_change, shift, ewm, rolling), so row t of a
single full-panel computation equals the last row of an expanding computation up to t. That turns
O(n^2) into O(n): 39 seconds per run becomes milliseconds, which is what makes ~90 runs feasible.

This is NOT taken on trust. `verify()` below compares the fast path against the production
target_weights() on sampled dates and aborts if they differ at all. Measured: 0.000e+00 across 25
dates. If that ever changes, the fast path must be abandoned, not tuned.

The RATIO and CARRY sleeves normalise using `.iloc[-1]`, which IS look-ahead across a full panel.
They are zero and excluded here (TREND-only), which is the only reason this shortcut is legal.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.portfolio_mt5 import CONFIGS, _ivol, target_weights

REFERENCE = ROOT / "data" / "reference"
OUT = ROOT / "backtest_out" / "greedy"
COST_BPS = 3.0
WARMUP = 300
DD_TOLERANCE = 0.01        # "materially" — a removal may not worsen maxDD by more than 1pp

BASELINE = {"sharpe": 0.363, "cagr": 0.0269, "vol": 0.0824, "maxdd": -0.2059,
            "cost_yr": 0.00912, "code": "4d0e06ad576c00be", "data": "9ff394f01bb02981"}


def load_close():
    d = pd.read_csv(REFERENCE / "portfolio_D1.csv", index_col=0, parse_dates=True)
    cols = {c.rsplit("_", 1)[0]: c for c in d.columns if c.endswith("_close")}
    close = d[list(cols.values())]
    close.columns = list(cols.keys())
    return close.ffill().dropna(how="any").sort_index()


def weight_path(px, target_vol, max_leverage):
    """TREND-only weights for EVERY date, identical line-for-line to target_weights."""
    ret = px.pct_change().fillna(0.0)
    tsig = np.sign(px.pct_change(252)).shift(1).fillna(0.0)
    tw = tsig * _ivol(ret)
    tw = tw.div(tw.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    port_ret = (tw.shift(1) * ret).sum(axis=1)
    realized = (port_ret.ewm(span=252).std() * np.sqrt(252)).clip(lower=1e-4)
    scale = (target_vol / realized).clip(0, max_leverage)
    return tw.mul(scale, axis=0)


def verify(close, cfg, n=15):
    rng = np.random.default_rng(0)
    P = weight_path(close, cfg["target_vol"], cfg["max_leverage"])
    worst = 0.0
    for i in rng.choice(range(400, len(close)), n, replace=False):
        w, _ = target_weights(close.iloc[:i], carry_signs={}, **cfg)
        worst = max(worst, float((w.reindex(close.columns).fillna(0.0) - P.iloc[i - 1]).abs().max()))
    return worst


def evaluate(close, cols, cfg):
    px = close[cols].dropna(how="any")
    P = weight_path(px, cfg["target_vol"], cfg["max_leverage"])
    # ALIGNMENT, and this is where a look-ahead bug lives. The production loop computes the weight
    # from close.iloc[:i] -- data strictly BEFORE day i -- and applies it to day i's return. Row
    # i-1 of the full path is that weight, so the effective book on day i is P.shift(1).
    # Multiplying P by the same day's return uses information the strategy did not have and
    # inflated Sharpe from 0.363 to 0.437. Caught by the reproduce-the-baseline guard.
    W = P.shift(1).iloc[WARMUP:]
    ret = px.pct_change().fillna(0.0).loc[W.index]
    gross = (W * ret).sum(axis=1)
    turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
    net = gross - turn * COST_BPS / 1e4
    eq = (1 + net).cumprod()
    dd = eq / eq.cummax() - 1
    yrs = len(net) / 252.0
    by_year = net.groupby(net.index.year).apply(lambda s: (1 + s).prod() - 1)
    return {
        "n_symbols": len(cols), "symbols": list(cols),
        "sharpe": float(net.mean() / net.std() * np.sqrt(252)),
        "gross_sharpe": float(gross.mean() / gross.std() * np.sqrt(252)),
        "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1),
        "vol": float(net.std() * np.sqrt(252)),
        "maxdd": float(dd.min()),
        "cost_yr": float((turn * COST_BPS / 1e4).sum() / yrs),
        "turnover_day": float(turn.mean()),
        "positive_years": f"{int((by_year > 0).sum())}/{len(by_year)}",
        "start": str(W.index[0].date()), "end": str(W.index[-1].date()),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    close = load_close()
    cfg = dict(CONFIGS["funded"])
    cfg["sleeves"] = ("TREND",)

    err = verify(close, cfg)
    print(f"parity check vs production target_weights: max diff {err:.3e}")
    if err > 0:
        raise SystemExit("fast path is NOT identical to production — aborting rather than tuning")

    cur = list(close.columns)
    base = evaluate(close, cur, cfg)
    print(f"\nreproduced baseline: sharpe {base['sharpe']:.3f}  maxDD {base['maxdd']:.2%}  "
          f"CAGR {base['cagr']:.2%}  vol {base['vol']:.2%}  cost {base['cost_yr']:.3%}/yr")
    d_s = abs(base["sharpe"] - BASELINE["sharpe"])
    print(f"  vs LOCKED baseline sharpe {BASELINE['sharpe']}: diff {d_s:.4f} "
          f"({'MATCHES' if d_s < 0.005 else '!! DOES NOT MATCH — investigate before proceeding'})")
    if d_s >= 0.005:
        raise SystemExit("cannot reproduce the locked baseline; greedy search would be meaningless")

    history = [{"round": 0, "removed": None, **base}]
    rejected = []          # permanent: a rejected modification is not retested without a new mechanism
    rnd = 0
    while len(cur) > 3:
        rnd += 1
        trials = []
        for s in cur:
            r = evaluate(close, [c for c in cur if c != s], cfg)
            r["removed"] = s
            r["d_sharpe"] = r["sharpe"] - base["sharpe"]
            r["d_maxdd"] = r["maxdd"] - base["maxdd"]
            trials.append(r)
        # OPERATOR ACCEPTANCE RULE, in strict priority order:
        #   1 net Sharpe  2 max drawdown  3 annual costs  4 turnover  5 CAGR
        # Sharpe decides; the rest break ties, so a variant never wins on turnover alone.
        trials.sort(key=lambda x: (-round(x["sharpe"], 4), -round(x["maxdd"], 4),
                                   round(x["cost_yr"], 6), round(x["turnover_day"], 6),
                                   -x["cagr"]))
        print(f"\n--- round {rnd}  (universe {len(cur)}) ---")
        for t in trials:
            ok = t["d_sharpe"] > 0 and t["d_maxdd"] >= -DD_TOLERANCE
            print(f"  drop {t['removed']:<8} sharpe {t['sharpe']:6.3f} ({t['d_sharpe']:+.3f})  "
                  f"maxDD {t['maxdd']:7.2%} ({t['d_maxdd']:+.2%})  "
                  f"cost {t['cost_yr']:.3%}  {'<-- ELIGIBLE' if ok else ''}")

        eligible = [t for t in trials if t["d_sharpe"] > 0 and t["d_maxdd"] >= -DD_TOLERANCE]
        rejected.extend([{"round": rnd, "removed": t["removed"], "d_sharpe": t["d_sharpe"],
                          "d_maxdd": t["d_maxdd"], "reason":
                          "sharpe did not improve" if t["d_sharpe"] <= 0
                          else f"drawdown worsened by more than {DD_TOLERANCE:.0%}"}
                         for t in trials if t not in eligible])
        best = eligible[0] if eligible else None
        if best is None:
            print(f"\n  no single removal improves Sharpe without worsening drawdown "
                  f"by more than {DD_TOLERANCE:.0%} — STOP")
            break
        cur = [c for c in cur if c != best["removed"]]
        base = {k: v for k, v in best.items() if k not in ("removed", "d_sharpe", "d_maxdd")}
        history.append({"round": rnd, **best})
        print(f"\n  ACCEPTED: remove {best['removed']} -> sharpe {best['sharpe']:.3f}, "
              f"maxDD {best['maxdd']:.2%}, universe now {len(cur)}")

    print("\n" + "=" * 78)
    print(" FINAL")
    print("=" * 78)
    print(f"  universe   {cur}")
    print(f"  sharpe     {base['sharpe']:.3f}   (locked baseline {BASELINE['sharpe']})")
    print(f"  gross Sh   {base['gross_sharpe']:.3f}")
    print(f"  CAGR       {base['cagr']:.2%}")
    print(f"  vol        {base['vol']:.2%}")
    print(f"  maxDD      {base['maxdd']:.2%}   (locked {BASELINE['maxdd']:.2%})")
    print(f"  cost/yr    {base['cost_yr']:.3%}   (locked {BASELINE['cost_yr']:.3%})")
    print(f"  turnover   {base['turnover_day']:.4f}/day")
    print(f"  pos years  {base['positive_years']}")

    pd.DataFrame(rejected).to_csv(OUT / "rejected_modifications.csv", index=False)
    json.dump({"locked_baseline": BASELINE, "history": history, "final": base,
               "rejected": rejected,
               "acceptance_rule_priority": ["net_sharpe", "max_drawdown", "annual_costs",
                                            "turnover", "cagr"],
               "rule": f"remove iff d_sharpe > 0 and d_maxdd >= -{DD_TOLERANCE}",
               "parity_check_max_diff": err},
              open(OUT / "greedy_elimination.json", "w"), indent=1, default=str)
    pd.DataFrame(history).to_csv(OUT / "greedy_history.csv", index=False)
    print(f"\n  written -> {OUT}")


if __name__ == "__main__":
    main()
