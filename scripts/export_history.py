"""Export OHLC history for the portfolio universe from MT5. READ-ONLY: no orders, no changes.

    py scripts\\export_history.py            # D1 full history + H1 intraday
    py scripts\\export_history.py --m15      # also M15 (heavier; only if H1 proves too coarse)

WHY THIS EXISTS
---------------
fetch_daily() keeps only the CLOSE. Two things are impossible on close-only data, and both are
currently blocking:

  1. Backtesting a stop-loss. A stop fires INTRADAY. Without the high and the low there is no way
     to know whether price traded through the level, so every stop result would be invented.
  2. Measuring drawdown the way a prop firm measures it. FTMO evaluates equity intraday against a
     10% total / 5% daily limit. A close-only equity curve cannot see the excursion that breaches
     it. This is exactly the defect already recorded in the belief store as `prop_audit`:
     "pass-rate claim overstated: daily-close DD measurement + vol-target selection bias".

One export unblocks both. Output goes to data/mt5/ as parquet (falls back to CSV).

WHAT TO CHECK IN THE OUTPUT
---------------------------
The per-symbol bar counts and date ranges. MT5 serves whatever the broker chose to keep, and
brokers differ wildly on intraday depth -- a symbol with two years of H1 cannot support a
ten-year intraday backtest, and pretending otherwise is how a backtest becomes a story. The
report prints the LIMITING symbol explicitly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

OUT = Path(__file__).resolve().parents[1] / "data" / "mt5"


def grab(sym: str, tf, bars: int) -> pd.DataFrame | None:
    r = mt5.copy_rates_from_pos(sym, tf, 0, bars)
    if r is None or len(r) == 0:
        return None
    d = pd.DataFrame(r)
    d["time"] = pd.to_datetime(d["time"], unit="s", utc=True)
    keep = [c for c in ("time", "open", "high", "low", "close", "tick_volume", "spread")
            if c in d.columns]
    return d[keep].set_index("time").sort_index()


def write(frames: dict, label: str):
    OUT.mkdir(parents=True, exist_ok=True)
    if not frames:
        print(f"  {label}: NOTHING returned — nothing written")
        return
    panel = pd.concat(frames, axis=1)
    panel.columns = [f"{k}_{c}" for k, c in panel.columns]
    p = OUT / f"portfolio_{label}.parquet"
    try:
        panel.to_parquet(p)
    except Exception as e:
        p = OUT / f"portfolio_{label}.csv"
        panel.to_csv(p)
        print(f"  (parquet unavailable: {type(e).__name__} — wrote CSV)")
    print(f"  {label}: {panel.shape[0]:,} rows x {len(frames)} symbols -> {p.name}")

    print(f"  {'symbol':>8} {'bars':>8}  {'from':>12}  {'to':>12}")
    limiting, fewest = None, 10 ** 9
    for k, d in frames.items():
        print(f"  {k:>8} {len(d):>8,}  {str(d.index[0].date()):>12}  {str(d.index[-1].date()):>12}")
        if len(d) < fewest:
            limiting, fewest = k, len(d)
    print(f"  LIMITING SYMBOL: {limiting} with {fewest:,} bars — this caps every multi-asset "
          f"backtest on {label}, regardless of what the others have.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m15", action="store_true")
    ap.add_argument("--daily-bars", type=int, default=6000)
    ap.add_argument("--intraday-bars", type=int, default=200_000)
    a = ap.parse_args()

    if mt5 is None or not mt5.initialize():
        raise SystemExit("MetaTrader5 unavailable — run on the VPS with the terminal open")
    acct = mt5.account_info()
    print(f"account {acct.login} @ {acct.server}  (READ-ONLY export)\n")

    from scripts.portfolio_mt5 import resolve_symbols
    syms = resolve_symbols(verbose=True)
    print(f"\nresolved {len(syms)} symbols: {syms}\n")

    tfs = [("D1", mt5.TIMEFRAME_D1, a.daily_bars), ("H1", mt5.TIMEFRAME_H1, a.intraday_bars)]
    if a.m15:
        tfs.append(("M15", mt5.TIMEFRAME_M15, a.intraday_bars))

    for label, tf, bars in tfs:
        frames = {}
        for name, sym in syms.items():
            d = grab(sym, tf, bars)
            if d is None:
                print(f"  {name} ({sym}): NO DATA at {label}")
                continue
            frames[name] = d
        write(frames, label)
        print()

    print("Nothing was ordered, modified or closed. This process only reads.")


if __name__ == "__main__":
    main()
