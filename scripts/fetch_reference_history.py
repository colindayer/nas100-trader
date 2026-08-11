"""Download 20+ years of daily OHLC for the portfolio universe. Runs anywhere with internet.

    python scripts/fetch_reference_history.py

WHY
---
FTMO's MT5 serves only what the broker chose to keep: COPPER 430 bars (from 2024-12-02), OIL
1,443, the indices 2,221. A fixed 13-symbol panel on that data cannot start before 2024-12-02 --
twenty months -- which is far too short to say anything about a trend strategy. The claim on
record ("2012-2026, 17/22 positive years") is not testable on broker data at all.

So the backtest uses reference series instead. These are NOT the traded CFDs, and that is a
DECLARED DEVIATION, not a detail:

  * futures continuations (GC=F gold, SI=F silver, CL=F WTI, HG=F copper) roll between contracts;
    a CFD does not. Roll gaps are real price moves in the series and are not tradeable as shown.
  * cash indices (^NDX, ^GSPC) exclude dividends and the CFD's financing.
  * FX spot from Yahoo is mid, not the broker's bid/ask.

What this data CAN establish: whether the strategy has any historical edge at all, over a period
long enough to contain multiple regimes. What it CANNOT establish: the exact P&L you would have
received at FTMO. For that, the broker series is the authority -- and the broker series is twenty
months long. Both facts belong in any conclusion drawn from this.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "reference"

# internal name -> Yahoo ticker. Chosen to match the traded instrument as closely as free data
# allows; every mismatch is listed in the module docstring.
TICKERS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F", "COPPER": "HG=F",
    "NAS100": "^NDX", "SP500": "^GSPC",
}
START = "2000-01-01"


def main():
    import yfinance as yf
    OUT.mkdir(parents=True, exist_ok=True)
    frames = {}
    for name, tk in TICKERS.items():
        print(f"  {name:<8} {tk:<10} ...", end=" ", flush=True)
        try:
            d = yf.download(tk, start=START, progress=False, auto_adjust=False)
        except Exception as e:
            print(f"FAILED {type(e).__name__}")
            continue
        if d is None or len(d) == 0:
            print("NO DATA")
            continue
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d = d[["Open", "High", "Low", "Close"]].rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
        d.index = pd.to_datetime(d.index).tz_localize(None)
        d = d[~d.index.duplicated(keep="last")].sort_index().dropna()
        frames[name] = d
        print(f"{len(d):,} bars  {d.index[0].date()} -> {d.index[-1].date()}")

    if not frames:
        raise SystemExit("nothing downloaded")

    panel = pd.concat(frames, axis=1)
    panel.columns = [f"{a}_{b}" for a, b in panel.columns]
    p = OUT / "portfolio_D1.csv"
    panel.to_csv(p)
    print(f"\n  {panel.shape[0]:,} rows x {len(frames)} symbols -> {p}")

    first = {k: v.index[0] for k, v in frames.items()}
    limiting = max(first, key=lambda k: first[k])
    print(f"  limiting symbol: {limiting} starts {first[limiting].date()} — "
          f"a FULL-universe panel cannot begin before this")
    print("\n  These are reference series, NOT the traded CFDs. See the module docstring.")


if __name__ == "__main__":
    main()
