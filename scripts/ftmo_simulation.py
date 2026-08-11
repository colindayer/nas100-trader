"""FROZEN BASELINE V1-COMPLETE + FTMO prop-rule simulation.

    python scripts/ftmo_simulation.py

FROZEN STRUCTURE (this is the freeze; only target_vol is left open, see below)
    signal      production target_weights(), TREND sleeve, lookback 252  [parity 0.000e+00]
    universe    GOLD SILVER OIL COPPER NAS100 SP500     (drop-FX: one mechanism decision)
    execution   no-trade band 0.005 per symbol
    costs       3 bps/side
    data        data/reference/portfolio_D1.csv, 2007-07-10 .. 2026-08-03

    target_vol stays a declared FREE PARAMETER because it is a pure scaling of the book: Sharpe
    is invariant to it (0.650-0.663 across 4-10%) while drawdown scales almost linearly. Choosing
    it by Sharpe is a category error. It is chosen HERE, by the prop constraints it actually binds.

WHY DRAWDOWN IS NOT ENOUGH, AND WHAT THIS SIMULATES
---------------------------------------------------
A backtest max drawdown is ONE number from ONE path. A challenge is a random start date and a
race between a profit target and two loss limits. The quantities that decide it are:

    P(pass)              hit the profit target before either limit
    P(breach total)      cumulative loss from initial balance reaches the max-loss limit
    P(breach daily)      a single day's loss from that day's start reaches the daily limit
    time to completion   how long the pass takes, which is the cost nobody models

FTMO rules applied (Challenge/Swing, standard at 2026-08):
    profit target   +10% phase 1, +5% phase 2
    max total loss  -10% of INITIAL balance (static)
    max daily loss  -5% of the day's STARTING equity
    no time limit

METHOD -- two independent estimators, because one is not evidence
    1 HISTORICAL PATHS: every possible start date in the real series, walked forward. Preserves
      the actual sequence, volatility clustering and crisis periods. Overlapping, so paths are
      not independent -- reported as a frequency, not a confidence interval.
    2 STATIONARY BOOTSTRAP (Politis-Romano, mean block 20d): resamples blocks to preserve
      autocorrelation while generating independent paths. An i.i.d. bootstrap would destroy the
      volatility clustering that causes drawdowns and would materially understate breach risk.

If the two disagree, the disagreement is the finding.
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
from scripts.exp_turnover import COST_BPS, V2, WARMUP, held_band
from scripts.exp_mechanism import weight_path_lb
from scripts.greedy_universe import load_close, verify
from scripts.portfolio_mt5 import CONFIGS, target_weights

OUT = ROOT / "backtest_out" / "frozen_v1"
BAND, LOOKBACK, MAX_LEV = 0.005, 252, 3.0
VOL_GRID = [0.04, 0.05, 0.06, 0.08]

TARGET_P1, TARGET_P2 = 0.10, 0.05
MAX_TOTAL_LOSS, MAX_DAILY_LOSS = 0.10, 0.05
MAX_DAYS = 252 * 5


def net_returns(px, target_vol):
    P = weight_path_lb(px, target_vol, MAX_LEV, LOOKBACK)
    W = held_band(P, BAND).iloc[WARMUP:]
    r = px.pct_change().fillna(0.0).loc[W.index]
    turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
    return (W * r).sum(axis=1) - turn * COST_BPS / 1e4


def simulate(path, target):
    """One challenge attempt. Returns (outcome, days).

    Daily loss is measured against the day's STARTING equity, which is how FTMO evaluates it --
    not against the initial balance, and not close-to-close on the equity curve."""
    eq = 1.0
    for i, r in enumerate(path, 1):
        if r <= -MAX_DAILY_LOSS:
            return "breach_daily", i
        eq *= (1 + r)
        if eq - 1 <= -MAX_TOTAL_LOSS:
            return "breach_total", i
        if eq - 1 >= target:
            return "pass", i
    return "timeout", len(path)


def historical(rets, target):
    a = rets.to_numpy()
    out = []
    for s in range(0, len(a) - 252):          # need at least a year of runway
        out.append(simulate(a[s:s + MAX_DAYS], target))
    return out


def stationary_bootstrap(rets, target, n=4000, mean_block=20, seed=7):
    a = rets.to_numpy()
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    out = []
    for _ in range(n):
        path = np.empty(MAX_DAYS)
        i = rng.integers(len(a))
        for t in range(MAX_DAYS):
            path[t] = a[i]
            i = rng.integers(len(a)) if rng.random() < p else (i + 1) % len(a)
        out.append(simulate(path, target))
    return out


def summarise(res):
    n = len(res)
    c = pd.Series([r[0] for r in res]).value_counts()
    days = [d for o, d in res if o == "pass"]
    return {"n": n,
            "pass_%": 100 * c.get("pass", 0) / n,
            "breach_total_%": 100 * c.get("breach_total", 0) / n,
            "breach_daily_%": 100 * c.get("breach_daily", 0) / n,
            "timeout_%": 100 * c.get("timeout", 0) / n,
            "median_days_to_pass": float(np.median(days)) if days else None,
            "p90_days_to_pass": float(np.percentile(days, 90)) if days else None}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    close = load_close()
    cfg = dict(CONFIGS["funded"]); cfg["sleeves"] = ("TREND",)
    err = verify(close, cfg)
    print(f"parity vs production target_weights: {err:.3e}")
    if err > 0:
        raise SystemExit("parity lost — refusing to freeze")

    px = close[V2].dropna(how="any")
    rows, sims = [], {}
    print(f"\n{'vol':>6}{'Sharpe':>8}{'maxDD':>9}{'CAGR':>8}"
          f"{'  | HISTORICAL PATHS: pass  bT   bD  tmo  medDays'}"
          f"{'  | BOOTSTRAP: pass  bT   bD  tmo  medDays'}")
    for tv in VOL_GRID:
        r = net_returns(px, tv)
        eq = (1 + r).cumprod()
        dd = float((eq / eq.cummax() - 1).min())
        yrs = len(r) / 252
        sh = float(r.mean() / r.std() * np.sqrt(252))
        cagr = float(eq.iloc[-1] ** (1 / yrs) - 1)
        h = summarise(historical(r, TARGET_P1))
        b = summarise(stationary_bootstrap(r, TARGET_P1))
        sims[f"vol_{tv}"] = {"phase1_historical": h, "phase1_bootstrap": b,
                             "sharpe": sh, "maxdd": dd, "cagr": cagr}
        rows.append({"target_vol": tv, "sharpe": sh, "maxdd": dd, "cagr": cagr, **
                     {f"hist_{k}": v for k, v in h.items()},
                     **{f"boot_{k}": v for k, v in b.items()}})
        print(f"{tv:6.2f}{sh:8.3f}{dd:9.2%}{cagr:8.2%}"
              f"   {h['pass_%']:5.1f}{h['breach_total_%']:5.1f}{h['breach_daily_%']:5.1f}"
              f"{h['timeout_%']:5.1f}{(h['median_days_to_pass'] or 0):9.0f}"
              f"   {b['pass_%']:5.1f}{b['breach_total_%']:5.1f}{b['breach_daily_%']:5.1f}"
              f"{b['timeout_%']:5.1f}{(b['median_days_to_pass'] or 0):9.0f}")

    print("\n  bT = breach max total loss (-10%)   bD = breach max daily loss (-5%)   "
          "tmo = no outcome in 5 years")

    data_sha = hashlib.sha256((ROOT / "data" / "reference" / "portfolio_D1.csv").read_bytes()
                              ).hexdigest()[:16]
    code_sha = hashlib.sha256((ROOT / "scripts" / "portfolio_mt5.py").read_bytes()).hexdigest()[:16]
    frozen = {
        "name": "BASELINE_V1_COMPLETE",
        "frozen_utc": "2026-08-03",
        "signal": "portfolio_mt5.target_weights, sleeves=('TREND',), lookback 252",
        "universe": V2, "band": BAND, "cost_bps_per_side": COST_BPS,
        "max_leverage": MAX_LEV,
        "target_vol": "FREE PARAMETER — pure scaling; chosen by prop constraints, not Sharpe",
        "parity_vs_production": err,
        "code_sha256_portfolio_mt5": code_sha, "data_sha256": data_sha,
        "rejected_permanently": {
            "periodic_rebalance_5d_10d": "Sharpe fell 0.063-0.070 despite 52-67% lower cost",
            "min_holding_5_10_20d": "drawdown worsened 2.75-5.56pp",
            "band_0.01_0.02": "no Sharpe gain over 0.005",
            "lookback_126": "train 0.768 -> OOS 0.546, overfit",
            "lookback_189_378": "unstable and worse on every metric",
            "CARRY": "unvalidatable: no deferred contracts for term structure; V2 has no FX",
            "leave_one_out_universe_search": "selection bias; train-selected 3-symbol universe "
                                             "collapsed 0.754 -> 0.316 out of sample",
        },
        "ftmo_simulation": sims,
    }
    json.dump(frozen, open(OUT / "BASELINE_V1_COMPLETE.json", "w"), indent=1, default=str)
    pd.DataFrame(rows).to_csv(OUT / "ftmo_simulation.csv", index=False)
    print(f"\n  FROZEN -> {OUT}/BASELINE_V1_COMPLETE.json   (code {code_sha}, data {data_sha})")


if __name__ == "__main__":
    main()
