"""EXPERIMENT H-volatility_targeting-har_sizing -- convert the one validated forecast into risk.

    python scripts/exp_har_sizing.py

WHAT IS AND IS NOT CHANGED
  The SIGNAL is untouched. Universe, 252-day trend, 0.005 band and 3bp costs are the frozen
  ones. The ONLY change is the denominator of the volatility targeter: the incumbent divides by
  a 252-day EWM of REALISED portfolio volatility, which is backward-looking by construction.
  This substitutes a HAR(1,5,22) FORECAST of tomorrow's volatility.

WHY THIS AND NOT SOMETHING ELSE
  HAR is the only component in this programme that beat a correct standard baseline and stayed
  beaten under attack: 8.0% out-of-sample QLIKE improvement over GARCH(1,1) on BTC daily
  volatility, n=709. Everything else either failed, or passed on an artifact. If a validated
  volatility forecast cannot improve a volatility-targeted book, the forecast has no economic
  content and the family closes.

NO LOOKAHEAD
  The HAR coefficients are re-fit on an EXPANDING window and used only for the following day.
  The first forecast is produced after a 3-year burn-in. Fitting once on the full sample would
  be the same look-ahead that inflated Sharpe 0.363 -> 0.437 earlier in this programme.

DECISION RULE, DECLARED BEFORE THE RUN
  Sizing changes are judged on realised-vol accuracy AND on the prop objective under REALISTIC
  TIME LIMITS, because Candidate V2 died by scoring well only when parking in cash was free.
  A variant is interesting only if it improves BOTH Sharpe and P(pass) at the 90/180-day limits.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exp_turnover import COST_BPS, V2, WARMUP, held_band
from scripts.exp_mechanism import _ivol
from scripts.greedy_universe import load_close
from scripts.candidate_v2_regime import ftmo_sweep, TIME_LIMITS

ANN, BAND, LOOKBACK, MAX_LEV, TARGET_VOL = 252, 0.005, 252, 3.0, 0.05
BURN = 756          # 3 years before the first forecast


def raw_weights(px):
    """The frozen signal, before any volatility scaling."""
    ret = px.pct_change().fillna(0.0)
    tsig = np.sign(px.pct_change(LOOKBACK)).shift(1).fillna(0.0)
    tw = tsig * _ivol(ret)
    return tw.div(tw.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0), ret


def har_vol_forecast(port_ret: pd.Series) -> pd.Series:
    """Expanding-window HAR(1,5,22) forecast of tomorrow's volatility. No look-ahead."""
    rv = port_ret.pow(2)
    lr = np.log(rv.replace(0, np.nan)).ffill()
    d = pd.concat({"d": lr, "w": lr.rolling(5).mean(), "m": lr.rolling(22).mean()}, axis=1)
    out = pd.Series(np.nan, index=port_ret.index)
    y = lr.shift(-1)
    Xall = d.to_numpy()
    yall = y.to_numpy()
    for t in range(BURN, len(port_ret), 21):            # re-fit monthly, forecast daily
        m = ~np.isnan(Xall[:t]).any(1) & ~np.isnan(yall[:t])
        if m.sum() < 250:
            continue
        A = np.column_stack([np.ones(m.sum()), Xall[:t][m]])
        beta, *_ = np.linalg.lstsq(A, yall[:t][m], rcond=None)
        end = min(t + 21, len(port_ret))
        Xf = Xall[t:end]
        ok = ~np.isnan(Xf).any(1)
        pred = np.full(end - t, np.nan)
        pred[ok] = np.column_stack([np.ones(ok.sum()), Xf[ok]]) @ beta
        out.iloc[t:end] = np.sqrt(np.exp(pred)) * np.sqrt(ANN)
    return out.clip(lower=1e-4)


def build(px, mode):
    tw, ret = raw_weights(px)
    port = (tw.shift(1) * ret).sum(axis=1)
    if mode == "frozen_ewm":
        vol = (port.ewm(span=252).std() * np.sqrt(ANN)).clip(lower=1e-4)
    elif mode == "har":
        vol = har_vol_forecast(port)
    elif mode == "ewm60":
        vol = (port.ewm(span=60).std() * np.sqrt(ANN)).clip(lower=1e-4)
    else:
        raise ValueError(mode)
    scale = (TARGET_VOL / vol).clip(0, MAX_LEV)
    W = held_band(tw.mul(scale, axis=0), BAND).iloc[WARMUP:].dropna(how="all")
    r = ret.loc[W.index]
    turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
    net = ((W * r).sum(axis=1) - turn * COST_BPS / 1e4).dropna()
    return net, vol, port


def stat(r):
    eq = (1 + r).cumprod(); yrs = len(r) / ANN
    dd = float((eq / eq.cummax() - 1).min())
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "vol": r.std() * np.sqrt(ANN),
            "Sharpe": r.mean() / r.std() * np.sqrt(ANN), "maxDD": dd,
            "vol_error": np.nan}


def main():
    px = load_close()[V2]
    print("=" * 96)
    print(" HAR VOLATILITY FORECAST AS THE SIZING DENOMINATOR")
    print(" signal frozen; only the vol-target denominator changes")
    print("=" * 96)

    runs = {}
    for mode in ("frozen_ewm", "ewm60", "har"):
        net, vol, port = build(px, mode)
        runs[mode] = (net, vol, port)

    # --- how well does each denominator actually track next-day realised vol?
    print("\n VOLATILITY TRACKING -- does the denominator predict what happens next?")
    print(f"  {'denominator':<16}{'corr w/ next |r|':>18}{'QLIKE':>10}{'realised vol':>14}")
    _, _, port = runs["frozen_ewm"]
    fut = port.abs().shift(-1) * np.sqrt(ANN)
    for mode in runs:
        _, vol, _ = runs[mode]
        d = pd.concat({"v": vol, "f": fut}, axis=1).dropna()
        d = d[(d["v"] > 0) & (d["f"] > 0)]
        x = (d["f"] ** 2) / (d["v"] ** 2)
        q = float((x - np.log(x) - 1).mean())
        net = runs[mode][0]
        print(f"  {mode:<16}{d['v'].corr(d['f']):>18.3f}{q:>10.3f}"
              f"{net.std()*np.sqrt(ANN):>14.2%}")

    print("\n PERFORMANCE (common sample)")
    common = runs["har"][0].index
    print(f"  {'denominator':<16}{'CAGR':>9}{'vol':>8}{'Sharpe':>9}{'maxDD':>9}")
    for mode in runs:
        s = stat(runs[mode][0].reindex(common).dropna())
        print(f"  {mode:<16}{s['CAGR']:>9.2%}{s['vol']:>8.2%}{s['Sharpe']:>9.2f}{s['maxDD']:>9.1%}")

    print("\n FTMO PHASE 1 UNDER TIME LIMITS -- the check that killed Candidate V2")
    for cap in (90, 180, 365):
        print(f"\n   --- {cap}d limit")
        print(f"  {'denominator':<16}{'pass%':>9}{'breach%':>10}{'timeout%':>10}{'med days':>10}")
        for mode in runs:
            s = ftmo_sweep(runs[mode][0].reindex(common).dropna(), cap)
            if s:
                print(f"  {mode:<16}{s['pass_%']:>9.1f}{s['breach_%']:>10.1f}"
                      f"{s['timeout_%']:>10.1f}{(s['median_days'] or 0):>10.0f}")

    # ponytail: the only thing that can silently ruin this is a peeking HAR fit
    net, vol, _ = runs["har"]
    assert vol.iloc[:BURN].isna().all(), "HAR produced a forecast inside the burn-in window"
    print(f"\n  self-check OK: no HAR forecast exists before the {BURN}-day burn-in")


if __name__ == "__main__":
    main()
