"""Trailing-exit study on the FROZEN six-asset baseline. Full 20-year panel.

    python scripts/exp_trailing.py

RECORDED, NOT RUN: the intraday entry-overlay study (VWAP / zone-reclaim) is dropped.
    Analytical ceiling: the entire execution budget is 0.181%/yr on a 5.31%-vol book, so PERFECT
    execution is worth +0.034 Sharpe, and a realistic third-of-spread saving +0.011. It touches
    only 35 direction flips a year. Against that, a deadline-or-miss rule risks missing trend
    entries, and variant C of the exit study showed missed trend participation costing 57 points
    of pass probability. Upside capped, downside structural.
    Data: intraday exists for 3 of 6 assets and only as ETF proxies (QQQ/SPY/GLD, 7y). SILVER,
    OIL and COPPER have none. No data purchased, no partial proxy universe substituted.

WHY TRAILING MIGHT SUCCEED WHERE FIXED TP/SL FAILED
---------------------------------------------------
Fixed TP/SL destroyed the strategy: pass probability 84% -> 27%. The mechanism was the TARGET --
it capped the few long trends that produce the entire return. A trailing stop has no target. It
ratchets with the position and exits only after a retracement, so a trend can run indefinitely.
That is a genuinely different hypothesis, not a re-test of a rejected one.

The objective is unchanged: does a trailing exit cut drawdown enough to run a HIGHER vol target
at no worse breach probability than the frozen 5% reference?

VARIANTS
    A rebalance_reversal  frozen baseline; a position leaves only when the target weight moves
    B atr_trail           chandelier: exit when price retraces k*ATR20 from the best level reached
                          since entry. Position then waits for a SIGNAL FLIP (trail replaces the
                          rebalance as the exit)
    C structure_trail     exit when the daily LOW breaks the lowest low of the prior N days
                          (mirror for shorts). Waits for a signal flip.
    D atr_trail + rebal   same ATR trail, but the daily rebalance may re-enter immediately
    E structure + rebal   same structure trail, rebalance may re-enter immediately

PREDECLARED PARAMETERS (fixed before any result; no grid search, no tuning of a winner)
    ATR trail distance   4x, 6x ATR20
    structure lookback   20, 40 days
Two values each, chosen as conventional defaults (Chandelier ~3-6 ATR; Donchian 20/40).

PRECISE STRUCTURE RULE, stated so it is reproducible:
    long  : exit if low_t  <  min(low[t-N .. t-1])      (prior N days, today excluded)
    short : exit if high_t >  max(high[t-N .. t-1])
    The exit price is that level, not the close. Fills assumed AT the level: optimistic, stated.

GUARD: variant A must reproduce the frozen baseline before any result is accepted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exp_exits import atr_pct, load_ohlc, stats_of
from scripts.exp_mechanism import weight_path_lb
from scripts.exp_turnover import COST_BPS, WARMUP, held_band
from scripts.ftmo_simulation import TARGET_P1, net_returns, stationary_bootstrap, summarise
from scripts.greedy_universe import load_close, verify
from scripts.portfolio_mt5 import CONFIGS

OUT = ROOT / "backtest_out" / "trailing"
BAND, LOOKBACK, MAX_LEV = 0.005, 252, 3.0
VOLS = [0.05, 0.06, 0.08]

VARIANTS = [
    ("A_rebalance_reversal", None, None, False),
    ("B_atr_trail_4", 4.0, None, False),
    ("B_atr_trail_6", 6.0, None, False),
    ("C_struct_trail_20", None, 20, False),
    ("C_struct_trail_40", None, 40, False),
    ("D_atr4_plus_rebal", 4.0, None, True),
    ("D_atr6_plus_rebal", 6.0, None, True),
    ("E_struct20_plus_rebal", None, 20, True),
    ("E_struct40_plus_rebal", None, 40, True),
]


def run_trailing(ohlc, W, atr_k, struct_n, allow_reentry):
    C, H, L = ohlc["close"], ohlc["high"], ohlc["low"]
    A = atr_pct(H, L, C).fillna(0.02)
    dates = W.index
    ci, hi, li, ai = (X.loc[dates].to_numpy() for X in (C, H, L, A))
    tgt = W.to_numpy()
    # prior-N extremes, today EXCLUDED (shift 1) -- no look-ahead
    lowN = {n: L.loc[dates].rolling(n).min().shift(1).to_numpy() for n in (20, 40)}
    highN = {n: H.loc[dates].rolling(n).max().shift(1).to_numpy() for n in (20, 40)}

    n, m = len(dates), W.shape[1]
    pos = np.zeros(m)
    best = np.zeros(m)                 # best level reached since entry (high if long, low if short)
    blocked_dir = np.zeros(m)
    rets, turns, exits = np.zeros(n), np.zeros(n), 0

    for t in range(1, n):
        want = tgt[t].copy()
        for i in range(m):
            if blocked_dir[i] != 0:
                if want[i] != 0 and np.sign(want[i]) != blocked_dir[i]:
                    blocked_dir[i] = 0.0
                else:
                    want[i] = 0.0
        turns[t] = np.abs(want - pos).sum()
        for i in range(m):
            if want[i] != 0 and (pos[i] == 0 or np.sign(want[i]) != np.sign(pos[i])):
                best[i] = ci[t - 1, i]          # reset the trail anchor on a new/flipped position
            elif want[i] == 0:
                best[i] = 0.0
        pos = want

        day_ret = np.zeros(m)
        prev_c = ci[t - 1]
        for i in range(m):
            w = pos[i]
            if w == 0:
                continue
            long = w > 0
            best[i] = max(best[i], hi[t, i]) if long else (
                min(best[i], li[t, i]) if best[i] > 0 else li[t, i])
            exit_px = None
            if atr_k is not None:
                d = ai[t, i] if np.isfinite(ai[t, i]) and ai[t, i] > 0 else 0.02
                lvl = best[i] * (1 - atr_k * d) if long else best[i] * (1 + atr_k * d)
                if (long and li[t, i] <= lvl) or ((not long) and hi[t, i] >= lvl):
                    exit_px = lvl
            if exit_px is None and struct_n is not None:
                lvl = lowN[struct_n][t, i] if long else highN[struct_n][t, i]
                if np.isfinite(lvl) and ((long and li[t, i] <= lvl) or
                                         ((not long) and hi[t, i] >= lvl)):
                    exit_px = lvl
            if exit_px is not None:
                day_ret[i] = w * (exit_px / prev_c[i] - 1)
                # CHARGE THE EXIT LEG. turns[t] was computed at rebalance time, before this stop
                # fired, so without this the exit is free and only the re-entry is paid for. With
                # 2,791 exits that is half a round trip missing on every one of them.
                turns[t] += abs(w)
                if not allow_reentry:
                    blocked_dir[i] = np.sign(w)
                pos[i] = 0.0
                best[i] = 0.0
                exits += 1
            else:
                day_ret[i] = w * (ci[t, i] / prev_c[i] - 1)
        rets[t] = day_ret.sum()

    net = pd.Series(rets - turns * COST_BPS / 1e4, index=dates)
    tser = pd.Series(turns, index=dates)
    return net.iloc[WARMUP:], exits, tser.iloc[WARMUP:]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    close = load_close()
    cfg = dict(CONFIGS["funded"]); cfg["sleeves"] = ("TREND",)
    err = verify(close, cfg)
    print(f"parity vs production target_weights: {err:.3e}")
    if err > 0:
        raise SystemExit("parity lost")
    ohlc = load_ohlc(); px = ohlc["close"]

    # ---- GUARD: variant A must reproduce the frozen baseline
    print("\nGUARD — variant A vs frozen baseline:")
    for tv in VOLS:
        ref = net_returns(px, tv)
        W = held_band(weight_path_lb(px, tv, MAX_LEV, LOOKBACK), BAND)
        got, _, _ = run_trailing(ohlc, W, None, None, False)
        a, b = stats_of(ref), stats_of(got)
        nd = int(((ref.reindex(got.index) - got).abs() > 1e-9).sum())
        ok = abs(a["sharpe"] - b["sharpe"]) < 0.001 and nd <= 1
        print(f"  vol {tv:.2f}  frozen {a['sharpe']:.4f}/{a['maxdd']:.2%}  "
              f"engine {b['sharpe']:.4f}/{b['maxdd']:.2%}  differing days {nd}  "
              f"{'OK' if ok else 'FAIL'}")
        if not ok:
            raise SystemExit("variant A does not reproduce the frozen baseline — results void")

    tr_px, oo_px = px.loc[:"2016-12-31"], px.loc["2017-01-01":]
    tr_oh = {k: v.loc[:"2016-12-31"] for k, v in ohlc.items()}
    oo_oh = {k: v.loc["2017-01-01":] for k, v in ohlc.items()}

    ref_row, rows = None, []
    print(f"\n{'variant':<24}{'vol':>5}{'Sharpe':>8}{'maxDD':>9}{'CAGR':>7}{'turn':>7}{'cost':>7}"
          f"{'pos':>7}{'train':>7}{'oos':>7}{'exits':>7}{'pass%':>7}{'brch%':>7}{'days':>7}  verdict")
    for name, atr_k, struct_n, reent in VARIANTS:
        for tv in VOLS:
            W = held_band(weight_path_lb(px, tv, MAX_LEV, LOOKBACK), BAND)
            net, nex, tser = run_trailing(ohlc, W, atr_k, struct_n, reent)
            s = stats_of(net)
            turn = float(tser.mean())          # ACTUAL turnover, incl. stop exits
            Wt = held_band(weight_path_lb(tr_px, tv, MAX_LEV, LOOKBACK), BAND)
            Wo = held_band(weight_path_lb(oo_px, tv, MAX_LEV, LOOKBACK), BAND)
            s_tr = stats_of(run_trailing(tr_oh, Wt, atr_k, struct_n, reent)[0])["sharpe"]
            s_oo = stats_of(run_trailing(oo_oh, Wo, atr_k, struct_n, reent)[0])["sharpe"]
            b = summarise(stationary_bootstrap(net, TARGET_P1, n=1500))
            row = {"variant": name, "target_vol": tv, **s, "turnover_day": turn,
                   "cost_yr": float(turn * COST_BPS / 1e4 * 252), "n_exits": nex,
                   "train_sharpe": s_tr, "oos_sharpe": s_oo,
                   "pass_%": b["pass_%"], "breach_%": b["breach_total_%"],
                   "median_days": b["median_days_to_pass"]}
            if name.startswith("A_") and tv == 0.05:
                ref_row = row
            v = ""
            if ref_row and not name.startswith("A_"):
                faster = (row["median_days"] or 1e9) < (ref_row["median_days"] or 1e9)
                safer = row["breach_%"] <= ref_row["breach_%"]
                stable = s_oo >= s_tr - 0.15
                v = ("BEATS 5% REF" if faster and safer and stable else
                     "reject: OOS collapse" if faster and safer else
                     "faster but riskier" if faster else "no gain")
            rows.append({**row, "verdict": v})
            print(f"{name:<24}{tv:5.2f}{s['sharpe']:8.3f}{s['maxdd']:9.2%}{s['cagr']:7.2%}"
                  f"{turn:7.4f}{row['cost_yr']:7.3%}{s['positive_years']:>7}{s_tr:7.3f}{s_oo:7.3f}"
                  f"{nex:7d}{b['pass_%']:7.1f}{b['breach_total_%']:7.1f}"
                  f"{(b['median_days_to_pass'] or 0):7.0f}  {v}")

    R = pd.DataFrame(rows)
    R.to_csv(OUT / "trailing_variants.csv", index=False)
    print(f"\n  REFERENCE (frozen, vol 5%): pass {ref_row['pass_%']:.1f}%  "
          f"breach {ref_row['breach_%']:.1f}%  median {ref_row['median_days']:.0f}d  "
          f"Sharpe {ref_row['sharpe']:.3f}  maxDD {ref_row['maxdd']:.2%}")
    win = R[R["verdict"] == "BEATS 5% REF"].sort_values("median_days")
    print("\n" + "=" * 78)
    if len(win):
        w = win.iloc[0]
        print(f" KEEP: {w['variant']} @ vol {w['target_vol']:.0%} — pass {w['pass_%']:.1f}%, "
              f"breach {w['breach_%']:.1f}%, {w['median_days']:.0f}d, maxDD {w['maxdd']:.2%}")
    else:
        print(" REJECT ALL TRAILING VARIANTS — none reaches +10% faster at no worse breach risk.")
        print(" The frozen six-asset baseline with rebalance-reversal exits stands unchanged.")
    print("=" * 78)
    json.dump({"reference": ref_row, "results": rows,
               "entry_overlay_dropped": {
                   "reason": "analytical ceiling +0.034 Sharpe (perfect execution) on a 0.181%/yr "
                             "execution budget, touching 35 direction flips/yr; intraday data "
                             "exists for 3 of 6 assets and only as ETF proxies",
                   "no_data_purchased": True, "no_proxy_universe_substituted": True},
               "predeclared": {"atr_trail": [4.0, 6.0], "structure_lookback": [20, 40]}},
              open(OUT / "trailing_variants.json", "w"), indent=1, default=str)
    print(f"\n  written -> {OUT}")


if __name__ == "__main__":
    main()
