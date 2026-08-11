"""Turnover experiments 1-3 against CANDIDATE V2. One dimension per experiment.

    python scripts/exp_turnover.py

CANDIDATE V2 (not frozen): TREND-only, universe GOLD SILVER OIL COPPER NAS100 SP500
    Sharpe 0.650  maxDD -16.08%  CAGR 5.29%  cost 0.331%/yr  turnover 0.0438/day
    train 2007-16 0.555 / OOS 2017-26 0.560  -- selected by ONE mechanism decision (drop FX),
    not by search, which is why it did not degrade out of sample.

WHAT IS AND IS NOT MODIFIED
---------------------------
The SIGNAL is untouched. `target_weights()` still produces the daily target, and the fast weight
path is byte-identical to it (verified, 0.000e+00). These experiments change only how that target
is APPLIED -- when we trade toward it, and by how much. That is an execution-layer change, which
is why the strategy stays the same strategy.

  1 WEEKLY REBALANCE   act on the target every k trading days, hold in between
  2 NO-TRADE BAND      trade a symbol only when its target moves more than b from what we hold
  3 MIN HOLDING PERIOD a symbol's position may not change for h days after it changes

ACCEPTANCE RULE (operator, strict priority): 1 net Sharpe, 2 max drawdown, 3 annual costs,
4 turnover, 5 CAGR. A variant is eligible only if net Sharpe improves and drawdown does not worsen
by more than 1pp. Rejections are recorded permanently.

ON PARAMETER SELECTION -- stated, not hidden: each experiment tests a SMALL PREDECLARED set of
values. Picking the best of 3 is still selection over 3, so every value is reported and the winner
is re-checked on train/OOS split before it can become a baseline. A variant that wins in-sample
and degrades out-of-sample is rejected regardless of its full-sample number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.greedy_universe import load_close, weight_path, verify
from scripts.portfolio_mt5 import CONFIGS

OUT = ROOT / "backtest_out" / "turnover"
COST_BPS = 3.0
WARMUP = 300
DD_TOL = 0.01
V2 = ["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500"]

# PREDECLARED, before any result is seen
GRID_WEEKLY = [5, 10]           # trading days between rebalances (5 ~ weekly, 10 ~ fortnightly)
GRID_BAND = [0.005, 0.01, 0.02]  # absolute weight distance before trading a symbol
GRID_HOLD = [5, 10, 20]         # days a position is frozen after it changes


def held_baseline(P):
    return P.shift(1)


def held_periodic(P, k):
    """Act on the target every k-th trading day; hold in between."""
    mask = np.zeros(len(P), dtype=bool)
    mask[::k] = True
    Q = P.where(pd.Series(mask, index=P.index), other=np.nan).ffill()
    return Q.shift(1)


def held_band(P, b):
    """Trade symbol i only when |target_i - held_i| > b. Per symbol, not portfolio-wide."""
    # weight_path's first row is NaN (ewm.std of a single point). Carrying NaN as the held state
    # makes every |target - held| > b comparison False forever, so the book never trades and the
    # variant silently returns a flat zero curve. Zero-fill before the loop.
    t = np.nan_to_num(P.to_numpy(), nan=0.0)
    h = np.empty_like(t)
    cur = t[0].copy()
    for i in range(len(t)):
        move = np.abs(t[i] - cur) > b
        cur = np.where(move, t[i], cur)
        h[i] = cur
    return pd.DataFrame(h, index=P.index, columns=P.columns).shift(1)


def held_minhold(P, days):
    """After a symbol's weight changes, freeze it for `days` bars."""
    t = np.nan_to_num(P.to_numpy(), nan=0.0)      # same NaN-seed hazard as held_band
    h = np.empty_like(t)
    cur = t[0].copy()
    lock = np.zeros(t.shape[1], dtype=int)
    for i in range(len(t)):
        free = lock <= 0
        changed = free & (t[i] != cur)
        cur = np.where(changed, t[i], cur)
        lock = np.where(changed, days, np.maximum(lock - 1, 0))
        h[i] = cur
    return pd.DataFrame(h, index=P.index, columns=P.columns).shift(1)


def stats(W, ret):
    W = W.iloc[WARMUP:]
    r = ret.loc[W.index]
    gross = (W * r).sum(axis=1)
    turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
    net = gross - turn * COST_BPS / 1e4
    eq = (1 + net).cumprod()
    dd = eq / eq.cummax() - 1
    yrs = len(net) / 252.0
    by = net.groupby(net.index.year).apply(lambda s: (1 + s).prod() - 1)
    return {"sharpe": float(net.mean() / net.std() * np.sqrt(252)),
            "gross_sharpe": float(gross.mean() / gross.std() * np.sqrt(252)),
            "maxdd": float(dd.min()), "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1),
            "vol": float(net.std() * np.sqrt(252)),
            "cost_yr": float((turn * COST_BPS / 1e4).sum() / yrs),
            "turnover_day": float(turn.mean()),
            "positive_years": f"{int((by > 0).sum())}/{len(by)}"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    close = load_close()
    cfg = dict(CONFIGS["funded"]); cfg["sleeves"] = ("TREND",)
    err = verify(close, cfg)
    print(f"parity vs production target_weights: {err:.3e}")
    if err > 0:
        raise SystemExit("fast path diverged from production — abort")

    px = close[V2].dropna(how="any")
    ret = px.pct_change().fillna(0.0)
    P = weight_path(px, cfg["target_vol"], cfg["max_leverage"])
    base = stats(held_baseline(P), ret)
    print(f"\nCANDIDATE V2: sharpe {base['sharpe']:.3f}  maxDD {base['maxdd']:.2%}  "
          f"CAGR {base['cagr']:.2%}  cost {base['cost_yr']:.3%}  turn {base['turnover_day']:.4f}")

    # train / OOS split, used to reject anything that only works in-sample
    tr, oo = px.loc[:"2016-12-31"], px.loc["2017-01-01":]
    def split_stats(fn):
        out = {}
        for lbl, p in (("train", tr), ("oos", oo)):
            Pp = weight_path(p, cfg["target_vol"], cfg["max_leverage"])
            out[lbl] = stats(fn(Pp), p.pct_change().fillna(0.0))["sharpe"]
        return out

    experiments = []
    for k in GRID_WEEKLY:
        experiments.append((f"1_periodic_{k}d", lambda P, k=k: held_periodic(P, k)))
    for b in GRID_BAND:
        experiments.append((f"2_band_{b}", lambda P, b=b: held_band(P, b)))
    for h in GRID_HOLD:
        experiments.append((f"3_minhold_{h}d", lambda P, h=h: held_minhold(P, h)))

    rows, rejected = [], []
    print(f"\n  {'variant':<18}{'sharpe':>8}{'d':>8}{'maxDD':>9}{'d':>8}{'cost':>8}{'turn':>8}"
          f"{'train':>8}{'oos':>8}  verdict")
    for name, fn in experiments:
        s = stats(fn(P), ret)
        sp = split_stats(fn)
        d_sh = s["sharpe"] - base["sharpe"]
        d_dd = s["maxdd"] - base["maxdd"]
        eligible = d_sh > 0 and d_dd >= -DD_TOL
        stable = sp["oos"] >= sp["train"] - 0.15          # no material OOS collapse
        verdict = ("ACCEPT-CANDIDATE" if eligible and stable else
                   "reject: OOS degrades" if eligible and not stable else
                   "reject: no Sharpe gain" if d_sh <= 0 else "reject: drawdown")
        rows.append({"variant": name, **s, "d_sharpe": d_sh, "d_maxdd": d_dd,
                     "train_sharpe": sp["train"], "oos_sharpe": sp["oos"], "verdict": verdict})
        if not verdict.startswith("ACCEPT"):
            rejected.append({"variant": name, "reason": verdict, "d_sharpe": round(d_sh, 4)})
        print(f"  {name:<18}{s['sharpe']:8.3f}{d_sh:+8.3f}{s['maxdd']:9.2%}{d_dd:+8.2%}"
              f"{s['cost_yr']:8.3%}{s['turnover_day']:8.4f}{sp['train']:8.3f}{sp['oos']:8.3f}"
              f"  {verdict}")

    R = pd.DataFrame(rows)
    acc = R[R["verdict"].str.startswith("ACCEPT")].sort_values(
        by=["sharpe", "maxdd", "cost_yr", "turnover_day", "cagr"],
        ascending=[False, False, True, True, False])
    print("\n" + "=" * 78)
    if len(acc):
        w = acc.iloc[0]
        print(f" WINNER: {w['variant']}   sharpe {w['sharpe']:.3f} (V2 {base['sharpe']:.3f})  "
              f"maxDD {w['maxdd']:.2%}  cost {w['cost_yr']:.3%}  turn {w['turnover_day']:.4f}")
        print(f" train {w['train_sharpe']:.3f} / oos {w['oos_sharpe']:.3f}")
        print(f" NOTE: best of {len(experiments)} predeclared variants — selection over "
              f"{len(experiments)}, stated not hidden.")
    else:
        print(" NO VARIANT ACCEPTED — Candidate V2 stands unchanged.")
    print("=" * 78)

    R.to_csv(OUT / "turnover_experiments.csv", index=False)
    json.dump({"candidate_v2": base, "results": rows, "rejected": rejected,
               "grids": {"periodic_days": GRID_WEEKLY, "band": GRID_BAND, "minhold": GRID_HOLD},
               "acceptance": ["net_sharpe", "max_drawdown", "annual_costs", "turnover", "cagr"]},
              open(OUT / "turnover_experiments.json", "w"), indent=1)
    print(f"\n  written -> {OUT}")


if __name__ == "__main__":
    main()
