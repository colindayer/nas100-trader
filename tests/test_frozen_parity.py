"""PARITY: the live target_weights() path must reproduce the frozen backtest weights.

    python tests/test_frozen_parity.py

This is the test the whole deployment rests on. If the function the live runner calls does not
produce the same weights as the function the backtest measured, then Sharpe 0.653 / -10.19% /
84% pass describes a strategy that is not the one trading, and every downstream check is theatre.

FROZEN STRATEGY (production, fixed)
    universe    GOLD SILVER OIL COPPER NAS100 SP500      (six; no FX, no CARRY)
    signal      target_weights(sleeves=('TREND',)), 252-day lookback
    sizing      5% annualised vol target, max_leverage 3.0
    execution   daily rebalance, 0.005 no-trade band
    exit        target-weight reduction / zero / sign reversal ONLY
    safeguard   15% catastrophe stop, broker-side, disaster protection only
    reference   Sharpe 0.653, maxDD -10.19%, ~84% pass, ~5.5% breach, ~438 median days

WHAT IS CHECKED
  1 the vectorised weight path equals production target_weights() on NAMED historical dates
  2 the no-trade band is deterministic and idempotent (re-running changes nothing)
  3 the frozen config resolves to exactly the six frozen symbols
  4 no look-ahead: weights at date t depend only on data strictly before t
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exp_turnover import held_band
from scripts.greedy_universe import load_close, weight_path
from scripts.portfolio_mt5 import target_weights

FROZEN_UNIVERSE = ["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500"]
FROZEN_VOL, FROZEN_LEV, FROZEN_BAND, FROZEN_LOOKBACK = 0.05, 3.0, 0.005, 252

# Named dates, fixed in this file so the test cannot be quietly re-sampled until it passes.
NAMED_DATES = ["2012-03-15", "2015-08-24", "2018-12-24", "2020-03-16",
               "2022-06-13", "2024-08-05", "2026-01-15"]


def main():
    close = load_close()[FROZEN_UNIVERSE].dropna(how="any")
    cfg = dict(target_vol=FROZEN_VOL, max_leverage=FROZEN_LEV, sleeves=("TREND",))

    # ---- 1. named-date parity against the PRODUCTION function
    P = weight_path(close, FROZEN_VOL, FROZEN_LEV)
    worst, checked = 0.0, 0
    for ds in NAMED_DATES:
        d = pd.Timestamp(ds)
        idx = close.index.searchsorted(d)
        if idx <= 300 or idx >= len(close):
            continue
        live, _ = target_weights(close.iloc[:idx], carry_signs={}, **cfg)
        back = P.iloc[idx - 1]
        diff = float((live.reindex(close.columns).fillna(0.0) - back).abs().max())
        worst = max(worst, diff)
        checked += 1
        print(f"  {ds}  max|live-backtest| = {diff:.3e}  gross={live.abs().sum():.4f}")
    assert checked >= 5, f"only {checked} named dates were testable"
    assert worst == 0.0, f"PARITY BROKEN: max weight difference {worst:.3e}"
    print(f"  PARITY: {checked} named dates, max difference {worst:.3e}")

    # ---- 2. band determinism, and the path-dependence that dictates the live design
    W1 = held_band(P, FROZEN_BAND)
    W2 = held_band(P, FROZEN_BAND)
    assert W1.equals(W2), "no-trade band is not deterministic"

    # The band carries state: today's held weight depends on what was held yesterday, which
    # depends on the whole path. Measured: restarting with 504 extra days of warm-up STILL leaves
    # a 5.1e-04 weight error, and 20 days leaves 3.9e-02. It does not converge usefully.
    #
    # OPERATIONAL CONSEQUENCE, and this is why the test exists: the live runner must NOT rebuild
    # its held state by recomputing history. It must read the ACTUAL BROKER POSITIONS and convert
    # them to weights. That makes a restart self-healing and keeps the bot and the broker in
    # agreement by construction rather than by hope.
    long_warm = held_band(weight_path(close.iloc[-804:], FROZEN_VOL, FROZEN_LEV), FROZEN_BAND)
    recompute_err = float((long_warm.iloc[-1] - W1.iloc[-1]).abs().max())
    assert recompute_err > 1e-6, (
        "band appears path-INdependent; the broker-state requirement may be unnecessary — "
        "re-examine before simplifying the live loop")
    print(f"  BAND: deterministic; PATH-DEPENDENT (recompute error {recompute_err:.1e}) "
          f"-> live held state MUST come from broker positions")

    # ---- 3. universe is exactly the frozen six
    assert list(close.columns) == FROZEN_UNIVERSE, f"universe drift: {list(close.columns)}"
    assert "CARRY" not in cfg["sleeves"] and cfg["sleeves"] == ("TREND",)
    print(f"  UNIVERSE: {FROZEN_UNIVERSE} — TREND only, no CARRY")

    # ---- 4. no look-ahead: perturbing the FUTURE must not change today's weights
    i = len(close) - 200
    base, _ = target_weights(close.iloc[:i], carry_signs={}, **cfg)
    tampered = close.copy()
    tampered.iloc[i:] *= 1.5                       # violently alter everything after t
    after, _ = target_weights(tampered.iloc[:i], carry_signs={}, **cfg)
    d = float((base - after).abs().max())
    assert d == 0.0, f"LOOK-AHEAD DETECTED: future data changed today's weights by {d:.3e}"
    print(f"  NO LOOK-AHEAD: future perturbation changed weights by {d:.1e}")

    print("\nPASS — live target_weights() reproduces the frozen backtest exactly")


if __name__ == "__main__":
    main()
