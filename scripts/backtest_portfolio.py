"""The FIRST real backtest of portfolio_multisleeve. Run on the VPS, where the data is.

    py scripts\\backtest_portfolio.py --config funded
    py scripts\\backtest_portfolio.py --config funded --sleeves TREND

WHY THIS EXISTS
---------------
Nothing ever produced this strategy's historical performance numbers. `wf_2012_2026`
("Sharpe 0.62 active period 2012-2026, 17/22 positive years, maxDD -18.8%") is a hand-typed
string in registry/belief_v2.json, added by a promotion-plumbing commit that contained no
backtest, no equity curve and no trade list. The contract's only approved trial,
TR-a921975d8eef2571, is a gold/silver-ratio study that was never run and was explicitly ruled
"may not be cited as evidence" on 2026-07-28. A max drawdown cannot exist without an equity
curve, and an equity curve needs entries, exits, sizing, portfolio state, rebalancing and PnL.
None were ever computed.

PARITY BY CONSTRUCTION
----------------------
This calls `portfolio_mt5.target_weights` -- the SAME function the live runner calls -- rather
than reimplementing it. A reimplementation would drift from production the moment either side
changed, and "the backtest and the bot disagree" is the failure this whole exercise exists to
prevent. Entries, exits and sizing are therefore identical to live by definition: the strategy
holds target weights, and its EXIT is the weight changing. There is no separate exit rule, and
adding one would make this a different strategy.

WHAT THIS CAN AND CANNOT MEASURE -- read before quoting any number
------------------------------------------------------------------
CAN:  close-to-close equity, Sharpe, per-year returns, close-based max drawdown, turnover and
      costs, for whichever sleeves the data can actually drive.

CANNOT, on daily closes alone:
  * INTRADAY drawdown. FTMO checks equity intraday against 10% total / 5% daily. A close-based
    DD understates the excursion that fails you. This is the defect already recorded as
    `prop_audit`: "daily-close DD measurement". Pass --intraday to use exported H1 bars.
  * Any stop-loss or take-profit. A stop fires intraday. Not modelled here because it is not in
    the strategy.

CANNOT, ever, with the data MT5 provides:
  * THE CARRY SLEEVE. carry_signs comes from live broker swap_long/swap_short. MT5 serves no
    history for swap rates, so the sign that was in force in 2015 is unknowable. The deployed
    `funded` config is TREND+CARRY, which means HALF OF IT IS NOT BACKTESTABLE on this data.
    This script runs the sleeves it can drive and says so; it does not silently pretend the
    carry sleeve was tested. Reconstructing carry from rate differentials would be new research.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.portfolio_mt5 import CONFIGS, target_weights          # PRODUCTION function

DATA = ROOT / "data" / "mt5"
COST_BPS_PER_SIDE = 3.0        # strategy_contracts/portfolio_multisleeve.json: "3bps/side"


def load(label: str) -> pd.DataFrame | None:
    for p in (DATA / f"portfolio_{label}.parquet", DATA / f"portfolio_{label}.csv"):
        if p.exists():
            d = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(
                p, index_col=0, parse_dates=True)
            return d
    return None


def field(panel: pd.DataFrame, name: str) -> pd.DataFrame:
    """Columns are '<SYMBOL>_<field>'. Pull one field for every symbol."""
    cols = {c.rsplit("_", 1)[0]: c for c in panel.columns if c.endswith(f"_{name}")}
    out = panel[list(cols.values())].copy()
    out.columns = list(cols.keys())
    return out.sort_index()


def run(config: str, sleeves: tuple | None, warmup: int, intraday: bool):
    panel = load("D1")
    if panel is None:
        raise SystemExit(f"no daily export found in {DATA} — run scripts/export_history.py first")
    close = field(panel, "close").ffill().dropna(how="all")
    print(f"data: {close.shape[1]} symbols, {len(close):,} daily bars "
          f"{close.index[0].date()} -> {close.index[-1].date()}")

    # every symbol must be present for the cross-sectional sleeves to mean anything
    first_valid = close.apply(lambda s: s.first_valid_index())
    limiting = first_valid.idxmax()
    print(f"limiting symbol: {limiting} starts {first_valid.max().date()} — "
          f"the multi-asset backtest cannot begin before this")

    cfg = dict(CONFIGS[config])
    if sleeves:
        cfg["sleeves"] = tuple(sleeves)
    tested = tuple(s for s in cfg["sleeves"] if s != "CARRY")
    if "CARRY" in cfg["sleeves"]:
        print("\n  !! CARRY REQUESTED BUT NOT BACKTESTABLE: carry_signs comes from live broker "
              "swap rates,\n     which MT5 serves no history for. Running "
              f"{tested} only. The deployed '{config}' config is\n     "
              f"{tuple(cfg['sleeves'])}, so this validates PART of what is deployed, not all.")
    if not tested:
        raise SystemExit("nothing testable left after removing CARRY")
    cfg["sleeves"] = tested

    ret = close.pct_change().fillna(0.0)
    rows, weights = [], []
    prev_w = pd.Series(0.0, index=close.columns)
    for i in range(warmup, len(close)):
        # EXPANDING window, strictly past data -> no look-ahead. carry_signs empty = sleeve off.
        w, _ = target_weights(close.iloc[:i], carry_signs={}, **cfg)
        w = w.reindex(close.columns).fillna(0.0)
        gross_ret = float((w * ret.iloc[i]).sum())
        turnover = float((w - prev_w).abs().sum())
        cost = turnover * COST_BPS_PER_SIDE / 1e4
        rows.append({"date": close.index[i], "gross": gross_ret, "turnover": turnover,
                     "cost": cost, "net": gross_ret - cost})
        weights.append(w)
        prev_w = w

    d = pd.DataFrame(rows).set_index("date")
    eq = (1 + d["net"]).cumprod()
    dd = eq / eq.cummax() - 1
    yrs = len(d) / 252.0
    sharpe = d["net"].mean() / d["net"].std() * np.sqrt(252) if d["net"].std() > 0 else float("nan")

    by_year = d.groupby(d.index.year)["net"].apply(lambda s: (1 + s).prod() - 1)
    pos = int((by_year > 0).sum())

    print("\n" + "=" * 74)
    print(f" BACKTEST — config={config} sleeves={tested} costs={COST_BPS_PER_SIDE}bps/side")
    print("=" * 74)
    print(f"  period          {d.index[0].date()} -> {d.index[-1].date()}  ({yrs:.1f} years)")
    print(f"  total return    {eq.iloc[-1] - 1:+.1%}")
    print(f"  CAGR            {eq.iloc[-1] ** (1 / yrs) - 1:+.2%}" if yrs > 0 else "")
    print(f"  volatility      {d['net'].std() * np.sqrt(252):.1%}")
    print(f"  SHARPE          {sharpe:.2f}")
    print(f"  MAX DD (close)  {dd.min():.1%}")
    print(f"  positive years  {pos}/{len(by_year)}")
    print(f"  turnover        {d['turnover'].mean():.3f}/day   costs "
          f"{d['cost'].sum() / yrs * 100:.2f}%/yr")

    print(f"\n  {'year':>6} {'net':>9}")
    for y, v in by_year.items():
        print(f"  {y:>6} {v:>+9.1%}")

    claim = {"sharpe": 0.62, "positive_years": "17/22", "maxdd": -0.188}
    print("\n" + "-" * 74)
    print(f"  THE CLAIM ON RECORD (wf_2012_2026, hand-typed, no artifact): "
          f"Sharpe {claim['sharpe']}, {claim['positive_years']} positive years, "
          f"maxDD {claim['maxdd']:.1%}")
    print(f"  THIS MEASUREMENT:                                            "
          f"Sharpe {sharpe:.2f}, {pos}/{len(by_year)} positive years, maxDD {dd.min():.1%}")
    print("  These are not the same test: the claim covers 2012-2026 with CARRY included.")
    print("-" * 74)

    if intraday:
        h1 = load("H1")
        if h1 is None:
            print("\n  --intraday requested but no H1 export found — skipped")
        else:
            print(f"\n  H1 export present: {len(h1):,} bars. Intraday drawdown modelling is the "
                  "next\n  step and is what FTMO's 10%/5% rules actually require.")

    out = ROOT / "registry" / f"backtest_{config}_{'_'.join(tested)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"config": config, "sleeves": list(tested),
               "period": [str(d.index[0].date()), str(d.index[-1].date())],
               "years": round(yrs, 2), "sharpe": round(float(sharpe), 3),
               "total_return": round(float(eq.iloc[-1] - 1), 4),
               "vol": round(float(d["net"].std() * np.sqrt(252)), 4),
               "max_dd_close": round(float(dd.min()), 4),
               "positive_years": f"{pos}/{len(by_year)}",
               "by_year": {int(k): round(float(v), 4) for k, v in by_year.items()},
               "cost_bps_per_side": COST_BPS_PER_SIDE,
               "carry_excluded": "CARRY" in CONFIGS[config]["sleeves"],
               "caveats": ["close-based DD understates intraday excursion (prop_audit defect)",
                           "CARRY sleeve not backtestable: no swap-rate history in MT5",
                           "no stop-loss or take-profit — the strategy has none"]},
              open(out, "w"), indent=1)
    print(f"\n  written: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="funded", choices=list(CONFIGS))
    ap.add_argument("--sleeves", nargs="*", default=None,
                    help="override the config's sleeves, e.g. --sleeves TREND")
    ap.add_argument("--warmup", type=int, default=300,
                    help="bars reserved before the first weight (target_weights needs history)")
    ap.add_argument("--intraday", action="store_true")
    a = ap.parse_args()
    run(a.config, a.sleeves, a.warmup, a.intraday)


if __name__ == "__main__":
    main()
