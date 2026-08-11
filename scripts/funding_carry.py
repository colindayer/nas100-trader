"""MEASURE the perp funding carry. Long spot / short perp, delta-neutral.

    python scripts/funding_carry.py

WHAT THIS MEASURES, EXACTLY
  The short-perp leg receives the funding rate every 8h when funding is positive. Delta is
  hedged by an equal long spot position, so directional P&L cancels and the return stream IS
  the funding stream, less fees.

WHAT THIS DOES NOT MEASURE, AND WHY
  BASIS RISK. A delta-neutral book still marks to market on (perp - spot). No BTC SPOT series
  exists in this repository -- data/ holds USD-M futures only -- so the basis leg cannot be
  computed. Over a long horizon basis mean-reverts and cumulative return converges to
  cumulative funding, but the PATH is noisier than what is printed below, and a basis blowout
  is precisely what liquidates a levered carry book. Treat every Sharpe here as an UPPER BOUND.

  EXCHANGE RISK. Custody, withdrawal halts, ADL, and liquidation-engine behaviour are not
  modelled and are not modellable from price data. FTX paid excellent funding until it did not.

  BORROW / MARGIN COST on the spot leg is set by SPOT_FUNDING_COST_ANNUAL below, not measured.

Published comparison (see the session notes): SSRN reports Sharpe 6.1-6.45 on this trade for
2020-2025, decaying to 4.06 in 2024 and NEGATIVE in 2025. If this script reproduces the early
years and not the late ones, that is the finding, not a bug.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

TAKER_FEE = 0.00045           # Binance perp taker, per side
REBALANCES_PER_YEAR = 12      # assumed roll/rebalance cadence for the fee drag
SPOT_FUNDING_COST_ANNUAL = 0.0   # unlevered, own capital, no borrow. Raise to model margin.
PERIODS_PER_YEAR = 3 * 365    # 8-hourly funding


def load() -> pd.Series:
    f = pd.read_parquet(ROOT / "data" / "btcusdt_funding.parquet")["fundingRate"].astype(float)
    return f.sort_index()


def summarise(r: pd.Series, label: str) -> dict:
    """r is a per-8h net return stream on notional."""
    if len(r) < 10:
        return {}
    mu, sd = r.mean(), r.std(ddof=1)
    ann_ret = mu * PERIODS_PER_YEAR
    ann_vol = sd * np.sqrt(PERIODS_PER_YEAR)
    eq = (1 + r).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    return {"label": label, "n": len(r), "ann_return": ann_ret, "ann_vol": ann_vol,
            "sharpe": ann_ret / ann_vol if ann_vol > 0 else float("nan"),
            "max_dd": dd, "pct_positive": float((r > 0).mean()),
            "total": float(eq.iloc[-1] - 1)}


def main() -> None:
    f = load()
    fee_drag = 2 * TAKER_FEE * 2 * REBALANCES_PER_YEAR / PERIODS_PER_YEAR   # both legs
    spot_drag = SPOT_FUNDING_COST_ANNUAL / PERIODS_PER_YEAR
    net = f - fee_drag - spot_drag

    print(f"BTCUSDT funding carry -- long spot / short perp, delta-neutral")
    print(f"  {len(f)} funding events   {f.index[0].date()} -> {f.index[-1].date()}")
    print(f"  fee drag {fee_drag*PERIODS_PER_YEAR:.2%}/yr  "
          f"(taker {TAKER_FEE:.3%}/side, both legs, {REBALANCES_PER_YEAR} rebalances/yr)\n")

    rows = [summarise(net, "FULL SAMPLE")]
    for y in sorted({d.year for d in f.index}):
        rows.append(summarise(net[net.index.year == y], str(y)))
    rows = [r for r in rows if r]

    hdr = f"{'period':>12}{'n':>7}{'ann ret':>10}{'ann vol':>10}{'Sharpe':>9}{'maxDD':>9}{'%pos':>8}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['label']:>12}{r['n']:>7}{r['ann_return']:>10.2%}{r['ann_vol']:>10.2%}"
              f"{r['sharpe']:>9.2f}{r['max_dd']:>9.2%}{r['pct_positive']:>8.1%}")

    full = rows[0]
    print(f"\n  On $10,000 unlevered: ${full['ann_return']*10000:,.0f}/yr at "
          f"{full['ann_vol']:.1%} volatility.")
    print(f"  Sharpe {full['sharpe']:.2f} is an UPPER BOUND -- basis risk and exchange risk "
          f"are NOT in it.")
    print(f"  Capital for $50k/yr at this return: ${50000/full['ann_return']:,.0f}.")

    # ponytail: one self-check, the only thing that can silently break this
    assert abs(f.mean() * PERIODS_PER_YEAR - net.mean() * PERIODS_PER_YEAR
               - fee_drag * PERIODS_PER_YEAR - spot_drag * PERIODS_PER_YEAR) < 1e-9, \
        "net stream is not gross funding minus the declared drags"
    print("\n  self-check OK: net = gross funding - fees - spot carry cost")


if __name__ == "__main__":
    main()
