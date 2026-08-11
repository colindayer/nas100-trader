"""Exit study against FROZEN BASELINE V1-COMPLETE. Objective: CHALLENGE SPEED, not Sharpe.

    python scripts/exp_exits.py

THE QUESTION, stated precisely
------------------------------
The binding FTMO constraint is the -10% total loss; the daily rule never binds (0.0% across every
vol setting). Drawdown therefore caps the volatility target, and the volatility target determines
how long a challenge takes: 450 median days at vol 5%, 244 at vol 8%. So the exit study asks ONE
thing:

    Does any exit rule cut drawdown enough to run a HIGHER vol target at NO WORSE breach
    probability than the current 5% configuration (5.2% breach, 83.9% pass, 450 days)?

An exit rule that improves Sharpe but not that trade-off is not interesting here. An exit rule
that speeds up the challenge by raising breach risk is a worse deal in disguise and is rejected.

FROZEN AND UNCHANGED: universe, 252-day signal, no-trade band 0.005, 3bps/side, sizing.
Only the exit layer varies.

VARIANTS
    A rebalance_only     the frozen baseline: a position leaves only when the target weight moves
    B catastrophe_only   a wide broker-side stop from entry; meant to bind almost never
    C tpsl_only          ATR stop and target; after either fires the symbol stays FLAT until its
                         signal flips (so the exit genuinely replaces the rebalance)
    D tpsl_plus_rebal    same stops, but the daily rebalance may re-enter immediately

PREDECLARED DISTANCES (fixed before any result; deliberately few)
    catastrophe   15%, 20% adverse from entry     -- disaster stops, not trading stops
    ATR stop/target  4x/8x and 6x/12x ATR20       -- 2:1 reward:risk, the standard convention
Four exit configurations plus the baseline. No grid search; no tuning of a winner.

STOPS ARE CHECKED ON THE INTRADAY RANGE
    A stop fires when price TRADES through it, not when it closes through it. The reference panel
    carries daily high/low, so the check uses them. Using closes would understate stop frequency
    and flatter every variant -- the exact defect `prop_audit` recorded for drawdown measurement.
    Fills are assumed AT the stop level: optimistic (no gap slippage), and stated as such.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exp_turnover import COST_BPS, V2, WARMUP, held_band
from scripts.exp_mechanism import weight_path_lb
from scripts.ftmo_simulation import (MAX_DAYS, TARGET_P1, simulate,
                                     stationary_bootstrap, summarise)
from scripts.greedy_universe import load_close, verify
from scripts.portfolio_mt5 import CONFIGS

OUT = ROOT / "backtest_out" / "exits"
REFERENCE = ROOT / "data" / "reference"
BAND, LOOKBACK, MAX_LEV = 0.005, 252, 3.0
VOLS = [0.05, 0.06, 0.08]

VARIANTS = [
    ("A_rebalance_only", None, None, None, False),
    ("B_catastrophe_15", 0.15, None, None, True),
    ("B_catastrophe_20", 0.20, None, None, True),
    ("C_tpsl_4_8", None, 4.0, 8.0, False),
    ("C_tpsl_6_12", None, 6.0, 12.0, False),
    ("D_tpsl_4_8_rebal", None, 4.0, 8.0, True),
    ("D_tpsl_6_12_rebal", None, 6.0, 12.0, True),
]


def load_ohlc():
    d = pd.read_csv(REFERENCE / "portfolio_D1.csv", index_col=0, parse_dates=True)
    out = {}
    for f in ("open", "high", "low", "close"):
        cols = {c.rsplit("_", 1)[0]: c for c in d.columns if c.endswith(f"_{f}")}
        x = d[list(cols.values())]
        x.columns = list(cols.keys())
        out[f] = x
    idx = out["close"].ffill().dropna(how="any").index
    return {k: v.reindex(idx).ffill()[V2] for k, v in out.items()}


def atr_pct(h, l, c, n=20):
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()]).groupby(level=0).max()
    return (tr.rolling(n).mean() / c).shift(1)


def run_exits(ohlc, W, catastrophe, sl_atr, tp_atr, allow_reentry):
    """Daily loop with per-symbol position state, entry price and intraday stop checks."""
    C, H, L = ohlc["close"], ohlc["high"], ohlc["low"]
    A = atr_pct(H, L, C).fillna(0.02)
    dates = W.index
    cols = list(W.columns)
    ci, hi, li, ai = (X.loc[dates].to_numpy() for X in (C, H, L, A))
    tgt = W.to_numpy()

    n, m = len(dates), len(cols)
    pos = np.zeros(m)
    entry = np.zeros(m)
    blocked_dir = np.zeros(m)      # sign we were stopped OUT of; 0 = not blocked
    rets, turns = np.zeros(n), np.zeros(n)

    for t in range(1, n):
        # ---- REBALANCE FIRST, at the previous close.
        # held_band() already returns LAGGED weights, so tgt[t] is what we are meant to hold ON
        # day t. Rebalancing at the END of day t and earning day t+1 on it lags a second time and
        # is a real error: it moved variant A off the frozen baseline (0.614 vs 0.653).
        want = tgt[t].copy()
        for i in range(m):
            if blocked_dir[i] != 0:
                if want[i] != 0 and np.sign(want[i]) != blocked_dir[i]:
                    blocked_dir[i] = 0.0        # signal flipped -> allowed back in
                else:
                    want[i] = 0.0
        turns[t] = np.abs(want - pos).sum()
        for i in range(m):
            if want[i] != 0 and (pos[i] == 0 or np.sign(want[i]) != np.sign(pos[i])):
                entry[i] = ci[t - 1, i]         # entered at the price we rebalanced on
            elif want[i] == 0:
                entry[i] = 0.0
        pos = want

        # ---- then live through day t, checking stops against the INTRADAY range
        day_ret = np.zeros(m)
        prev_c = ci[t - 1]
        for i in range(m):
            w = pos[i]
            if w == 0:
                continue
            long = w > 0
            exit_px = None
            if catastrophe is not None and entry[i] > 0:
                lvl = entry[i] * (1 - catastrophe) if long else entry[i] * (1 + catastrophe)
                if (long and li[t, i] <= lvl) or ((not long) and hi[t, i] >= lvl):
                    exit_px = lvl
            if exit_px is None and sl_atr is not None and entry[i] > 0:
                dd = ai[t, i] if np.isfinite(ai[t, i]) and ai[t, i] > 0 else 0.02
                sl = entry[i] * (1 - sl_atr * dd) if long else entry[i] * (1 + sl_atr * dd)
                tp = entry[i] * (1 + tp_atr * dd) if long else entry[i] * (1 - tp_atr * dd)
                if (long and li[t, i] <= sl) or ((not long) and hi[t, i] >= sl):
                    exit_px = sl
                elif (long and hi[t, i] >= tp) or ((not long) and li[t, i] <= tp):
                    exit_px = tp
            if exit_px is not None:
                day_ret[i] = w * (exit_px / prev_c[i] - 1)
                if not allow_reentry:
                    blocked_dir[i] = np.sign(w)     # remember WHICH WAY we were stopped out
                pos[i] = 0.0
                entry[i] = 0.0
            else:
                day_ret[i] = w * (ci[t, i] / prev_c[i] - 1)
        rets[t] = day_ret.sum()

    net = pd.Series(rets - turns * COST_BPS / 1e4, index=dates)
    return net.iloc[WARMUP:]


def stats_of(net):
    eq = (1 + net).cumprod()
    dd = eq / eq.cummax() - 1
    yrs = len(net) / 252
    by = net.groupby(net.index.year).apply(lambda s: (1 + s).prod() - 1)
    return {"sharpe": float(net.mean() / net.std() * np.sqrt(252)),
            "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1),
            "maxdd": float(dd.min()), "vol": float(net.std() * np.sqrt(252)),
            "positive_years": f"{int((by > 0).sum())}/{len(by)}"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    close = load_close()
    cfg = dict(CONFIGS["funded"]); cfg["sleeves"] = ("TREND",)
    err = verify(close, cfg)
    print(f"parity vs production target_weights: {err:.3e}")
    if err > 0:
        raise SystemExit("parity lost")
    ohlc = load_ohlc()
    px = ohlc["close"]

    ref = None
    rows = []
    print(f"\n{'variant':<20}{'vol':>5}{'Sharpe':>8}{'maxDD':>9}{'CAGR':>7}{'turn':>7}{'cost':>7}"
          f"{'pass%':>7}{'breach%':>8}{'medDays':>8}  verdict")
    for name, cat, sl, tp, reent in VARIANTS:
        for tv in VOLS:
            P = weight_path_lb(px, tv, MAX_LEV, LOOKBACK)
            W = held_band(P, BAND)
            net = run_exits(ohlc, W, cat, sl, tp, reent)
            s = stats_of(net)
            turn = float(W.diff().abs().sum(axis=1).iloc[WARMUP:].mean())
            b = summarise(stationary_bootstrap(net, TARGET_P1, n=1500))
            row = {"variant": name, "target_vol": tv, **s, "turnover_day": turn,
                   "cost_yr": float(turn * COST_BPS / 1e4 * 252),
                   "pass_%": b["pass_%"], "breach_total_%": b["breach_total_%"],
                   "breach_daily_%": b["breach_daily_%"],
                   "median_days": b["median_days_to_pass"]}
            if name == "A_rebalance_only" and tv == 0.05:
                ref = row
            verdict = ""
            if ref and name != "A_rebalance_only":
                faster = (row["median_days"] or 1e9) < (ref["median_days"] or 1e9)
                safer = row["breach_total_%"] <= ref["breach_total_%"]
                verdict = ("BEATS 5% REF" if faster and safer else
                           "faster but riskier" if faster else "no gain")
            rows.append({**row, "verdict": verdict})
            print(f"{name:<20}{tv:5.2f}{s['sharpe']:8.3f}{s['maxdd']:9.2%}{s['cagr']:7.2%}"
                  f"{turn:7.4f}{row['cost_yr']:7.3%}{b['pass_%']:7.1f}{b['breach_total_%']:8.1f}"
                  f"{(b['median_days_to_pass'] or 0):8.0f}  {verdict}")

    R = pd.DataFrame(rows)
    R.to_csv(OUT / "exit_variants.csv", index=False)
    print(f"\n  REFERENCE (frozen, vol 5%): pass {ref['pass_%']:.1f}%  "
          f"breach {ref['breach_total_%']:.1f}%  median {ref['median_days']:.0f}d")
    win = R[R["verdict"] == "BEATS 5% REF"].sort_values("median_days")
    if len(win):
        w = win.iloc[0]
        print(f"  WINNER: {w['variant']} @ vol {w['target_vol']:.0%} — pass {w['pass_%']:.1f}%, "
              f"breach {w['breach_total_%']:.1f}%, {w['median_days']:.0f}d")
    else:
        print("  NO exit variant reaches the target faster at no worse breach risk. "
              "Frozen baseline stands.")
    json.dump(rows, open(OUT / "exit_variants.json", "w"), indent=1, default=str)
    print(f"\n  written -> {OUT}")


if __name__ == "__main__":
    main()
