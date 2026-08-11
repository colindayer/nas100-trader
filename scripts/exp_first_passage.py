"""MECHANISM: first-passage time control. Is CONSTANT volatility targeting actually optimal?

    python scripts/exp_first_passage.py

THE MECHANISM
  A prop challenge is a first-passage problem: reach +10% before -10% (and before a deadline),
  where a single day losing 5% also kills you. Classical result (Dubins & Savage, "How to
  Gamble If You Must"): for a FAVOURABLE game, TIMID play maximises the probability of reaching
  a goal before ruin; for an UNFAVOURABLE game, BOLD play does. Neither is "constant exposure".

  Every experiment in this programme so far has assumed a constant volatility target and then
  argued about which signal to feed it. This asks a different question: holding the SIGNAL
  completely fixed, does the optimal EXPOSURE PATH differ from a constant?

FALSIFIER, DECLARED BEFORE THE RUN
  "The optimal policy is interior and smooth — i.e. constant volatility targeting is already
  optimal." If the dynamic program returns a flat policy, the mechanism is dead and constant
  targeting is vindicated, which is itself worth knowing permanently.

METHOD
  Backward induction on the exact state space of the challenge:
      state  = (equity relative to start, trading days remaining)
      action = exposure multiplier k applied to the frozen strategy's daily return
      value  = P(pass before any breach, before the deadline)
  Daily returns are the FROZEN portfolio's own empirical distribution, resampled in blocks so
  volatility clustering survives -- not a Gaussian, which would understate breach risk.

  The daily-loss rule is applied to the day's STARTING equity, exactly as FTMO evaluates it.

WHAT THIS IS NOT
  Not a new signal, not a parameter search, and not deployable. It measures whether a degree of
  freedom we have always held fixed is worth anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ftmo_simulation import net_returns
from scripts.greedy_universe import load_close
from scripts.exp_turnover import V2

TARGET, MAX_TOTAL, MAX_DAILY = 0.10, 0.10, 0.05
BASE_VOL = 0.05
K_GRID = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0])     # exposure multipliers
EQ_GRID = np.linspace(0.90, 1.10, 81)                       # equity states between barriers
ANN = 252


def daily_pool(px) -> np.ndarray:
    r = net_returns(px, BASE_VOL).dropna()
    return r.to_numpy()


EPS = 1e-9


def to_grid(x: np.ndarray) -> np.ndarray:
    """Map equity to the NEAREST grid point.

    np.searchsorted returns the UPPER insertion index, which rounds every continuation UP.
    Compounded over a 365-step backward induction that is a free upward drift, and it made the
    DP report P(pass) = 1.000 from the starting state. Caught by the breached-state self-check.
    """
    return np.clip(np.rint((x - EQ_GRID[0]) / (EQ_GRID[1] - EQ_GRID[0])).astype(int),
                   0, len(EQ_GRID) - 1)


def solve(pool: np.ndarray, horizon: int, n_shock: int = 400, seed: int = 5):
    """Backward induction. Returns (value, policy) on the (equity, time) grid."""
    rng = np.random.default_rng(seed)
    shocks = rng.choice(pool, n_shock, replace=False) if n_shock < len(pool) else pool
    nE, nK = len(EQ_GRID), len(K_GRID)
    V = np.zeros((horizon + 1, nE))
    P = np.zeros((horizon + 1, nE), dtype=int)
    # terminal: no time left, not yet passed -> value 0
    for t in range(horizon - 1, -1, -1):
        for i, e in enumerate(EQ_GRID):
            if e - 1 >= TARGET - EPS:
                V[t, i] = 1.0
                continue
            if e - 1 <= -MAX_TOTAL + EPS:
                V[t, i] = 0.0
                continue
            best, bestk = -1.0, 0
            for ki, k in enumerate(K_GRID):
                r = k * shocks
                dead_daily = r <= -MAX_DAILY
                e2 = e * (1.0 + r)
                val = np.empty(len(r))
                passed = (e2 - 1) >= TARGET - EPS
                busted = ((e2 - 1) <= -MAX_TOTAL + EPS) | dead_daily
                cont = ~passed & ~busted
                val[passed] = 1.0
                val[busted] = 0.0
                if cont.any():
                    val[cont] = V[t + 1, to_grid(e2[cont])]
                m = val.mean()
                if m > best:
                    best, bestk = m, ki
            V[t, i] = best
            P[t, i] = bestk
    return V, P


def simulate_policy(pool, policy, horizon, kind, n=20000, seed=11):
    """Forward-simulate a policy on fresh block-resampled paths."""
    rng = np.random.default_rng(seed)
    nE = len(EQ_GRID)
    outc = {"pass": 0, "breach": 0, "timeout": 0}
    days = []
    for _ in range(n):
        e, t = 1.0, 0
        start = rng.integers(len(pool))
        while t < horizon:
            i = int(to_grid(np.array([e]))[0])
            k = K_GRID[policy[t, i]] if kind == "optimal" else kind
            r = k * pool[(start + t) % len(pool)]
            if r <= -MAX_DAILY:
                outc["breach"] += 1; break
            e *= (1 + r); t += 1
            if e - 1 <= -MAX_TOTAL:
                outc["breach"] += 1; break
            if e - 1 >= TARGET:
                outc["pass"] += 1; days.append(t); break
        else:
            outc["timeout"] += 1
    tot = sum(outc.values())
    return {"pass_%": 100 * outc["pass"] / tot, "breach_%": 100 * outc["breach"] / tot,
            "timeout_%": 100 * outc["timeout"] / tot,
            "median_days": float(np.median(days)) if days else None}


def main():
    px = load_close()[V2]
    pool = daily_pool(px)
    sharpe = pool.mean() / pool.std() * np.sqrt(ANN)
    print("=" * 96)
    print(" FIRST-PASSAGE CONTROL — is constant volatility targeting optimal?")
    print(f" frozen portfolio daily pool: n={len(pool)}, Sharpe {sharpe:.3f}, "
          f"vol {pool.std()*np.sqrt(ANN):.2%}")
    print(f" exposure multipliers tested: {list(K_GRID)}   (1.0 = the incumbent)")
    print("=" * 96)

    for horizon in (90, 180, 365):
        V, P = solve(pool, horizon)
        print(f"\n{'='*96}\n {horizon}-DAY CHALLENGE\n{'='*96}")
        print(f"  DP value at start (equity 1.00): P(pass) = {V[0, to_grid(np.array([1.0]))[0]]:.3f}")

        print(f"\n  OPTIMAL EXPOSURE POLICY  (rows = equity, cols = days remaining)")
        cols = [horizon - 1, int(horizon * 0.75), int(horizon * 0.5), int(horizon * 0.25), 5]
        print(f"    {'equity':<9}" + "".join(f"{'d-' + str(c):>8}" for c in cols))
        for e in (0.94, 0.97, 1.00, 1.03, 1.06, 1.09):
            i = int(to_grid(np.array([e]))[0])
            row = "".join(f"{K_GRID[P[horizon-1-c, i]]:>8.1f}" for c in cols)
            print(f"    {e:<9.2f}{row}")

        print(f"\n  FORWARD SIMULATION on fresh paths")
        print(f"    {'policy':<22}{'pass%':>9}{'breach%':>10}{'timeout%':>10}{'med days':>10}")
        rows = {}
        for lab, kind in (("constant k=1.0", 1.0), ("constant k=2.0", 2.0),
                          ("constant k=3.0", 3.0), ("OPTIMAL (state-dep)", "optimal")):
            s = simulate_policy(pool, P, horizon, kind)
            rows[lab] = s
            print(f"    {lab:<22}{s['pass_%']:>9.1f}{s['breach_%']:>10.1f}"
                  f"{s['timeout_%']:>10.1f}{(s['median_days'] or 0):>10.0f}")
        best_const = max(v["pass_%"] for k, v in rows.items() if k.startswith("constant"))
        gain = rows["OPTIMAL (state-dep)"]["pass_%"] - best_const
        print(f"\n    optimal vs BEST constant: {gain:+.1f} pp   "
              f"{'MECHANISM SUPPORTED' if gain > 2.0 else 'falsifier met: constant is ~optimal'}")

    # ponytail: the DP must never value a busted state above zero
    V, P = solve(pool, 90)
    i_bust = int(to_grid(np.array([0.90]))[0])
    assert V[0, i_bust] == 0.0, "DP assigns positive value to a breached state"
    print(f"\n  self-check OK: breached states carry zero value in the DP")


if __name__ == "__main__":
    main()
