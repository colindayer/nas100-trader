"""
intraday_momentum_test.py — gauntlet test of Zarattini/Aziz/Barbon (SSRN 4824172)
"Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)"
+ the Maróy (SSRN 5095349) finding that VWAP-based exits work best.

WHY THIS CANDIDATE (vs the usual rejects): same authors as the ORB paper our
validated S5 is built on; net-of-costs Sharpe 1.33 / +19.6%/yr on SPY 2007-2024
in the paper; trades ~daily (adds BREADTH → higher combined Sharpe → faster
prop passes); takes SHORTS (potential bear-regime diversifier vs our long-tilted
book). MUST still pass OUR gauntlet on OUR data before any adoption.

Rule (hourly-bar approximation of the paper):
  • Noise area: open_day ± sigma(t), sigma(t) = 14-day average of |price(t) −
    open_day| at the same hour-of-day.
  • Price crosses ABOVE upper boundary → long; BELOW lower → short (flip allowed).
  • Trailing stop at session VWAP (Maróy's best exit); hard exit at last bar.
  • Costs via SLIP from mean_reversion_test (same as every other test here).

Run LOCALLY (needs qqq_hourly_7y.csv / spy_hourly_7y.csv):
  python3 intraday_momentum_test.py
"""
import numpy as np
import pandas as pd
import warnings

from mean_reversion_test import load, SLIP

warnings.filterwarnings("ignore")


# (inlined from test_doc_strategies.py — importing that module runs its backtests)
def m_from_trades(trades, lo, hi):
    sel = [r for (dt, r) in trades if lo <= dt.year <= hi]
    t = pd.Series(sel)
    if len(t) == 0:
        return dict(n=0, wr=0, ret=0, sharpe=0, dd=0)
    eq = (1 + t).cumprod()
    return dict(n=len(t), wr=(t > 0).mean(), ret=eq.iloc[-1] - 1,
                sharpe=t.mean() / t.std() * np.sqrt(len(t)) if t.std() > 0 else 0,
                dd=(eq / eq.cummax() - 1).min())


def six_filters(IS, OOS, name):
    checks = {
        "[01] OOS Sharpe>0.5": OOS["sharpe"] > 0.5,
        "[02] maxDD>-35%":     OOS["dd"] > -0.35,
        "[03] OOS Sharpe<2.5": OOS["sharpe"] < 2.5,
        "[04] not overfit":    OOS["sharpe"] <= IS["sharpe"] * 1.3 + 0.5,
        "[05] >=30 trades":    OOS["n"] >= 30,
        "[06] IS Sharpe>0":    IS["sharpe"] > 0,
    }
    print(f"\n{'=' * 64}\n{name}")
    for lab, m in [("IS ", IS), ("OOS", OOS)]:
        print(f"  {lab}: n={m['n']:3d} wr={m['wr']:.0%} ret={m['ret']:+.1%} "
              f"Sharpe={m['sharpe']:.2f} DD={m['dd']:.1%}")
    for k, v in checks.items():
        print(f"    [{'PASS' if v else 'FAIL'}] {k}")
    print(f"  >>> {'✅ PASSES ALL SIX' if all(checks.values()) else '❌ REJECTED'}")
    return all(checks.values())

LOOKBACK = 14      # days for the noise boundary
START_H, END_H = 10, 15   # evaluate breakouts 10:00-15:00, exit on last bar


def day_frames(sym):
    df = load(sym)
    df = df.between_time("09:00", "16:00")
    df["Date"] = df.index.date
    return df


def run(sym):
    df = day_frames(sym)
    # per-day, per-hour abs deviation from the day's open
    opens = df.groupby("Date")["Open"].first()
    df["DayOpen"] = df["Date"].map(opens)
    df["Hour"] = df.index.hour
    df["AbsDev"] = (df["Close"] - df["DayOpen"]).abs()
    # sigma(t): rolling mean of AbsDev at same hour over prior LOOKBACK days
    piv = df.pivot_table(index="Date", columns="Hour", values="AbsDev")
    sigma = piv.rolling(LOOKBACK, min_periods=LOOKBACK).mean().shift(1)  # no lookahead

    trades = []
    for d, day in df.groupby("Date"):
        if d not in sigma.index:
            continue
        sig_row = sigma.loc[d]
        o = day["DayOpen"].iloc[0]
        # session VWAP (trailing stop level)
        tp = (day["High"] + day["Low"] + day["Close"]) / 3
        cum_v = day["Volume"].cumsum()
        vwap = (tp * day["Volume"]).cumsum() / cum_v.replace(0, np.nan)

        pos = 0          # +1 long, -1 short
        entry = 0.0
        pnl = 0.0
        for ts, bar in day.iterrows():
            h = ts.hour
            px = float(bar["Close"])
            vw = float(vwap.loc[ts]) if not np.isnan(vwap.loc[ts]) else px
            s = sig_row.get(h, np.nan)
            if np.isnan(s):
                continue
            upper, lower = o + s, o - s
            # trailing VWAP stop
            if pos == 1 and px < vw:
                pnl += (px - entry) / entry - SLIP
                pos = 0
            elif pos == -1 and px > vw:
                pnl += (entry - px) / entry - SLIP
                pos = 0
            # breakout entries / flips, within the entry window
            if START_H <= h <= END_H:
                if px > upper and pos <= 0:
                    if pos == -1:
                        pnl += (entry - px) / entry - SLIP
                    pos, entry = 1, px
                elif px < lower and pos >= 0:
                    if pos == 1:
                        pnl += (px - entry) / entry - SLIP
                    pos, entry = -1, px
        # exit at last bar of the day
        last = float(day["Close"].iloc[-1])
        if pos == 1:
            pnl += (last - entry) / entry - SLIP
        elif pos == -1:
            pnl += (entry - last) / entry - SLIP
        if pnl != 0.0:
            trades.append((pd.Timestamp(d), pnl))
    return trades


if __name__ == "__main__":
    for sym in ("QQQ", "SPY"):
        try:
            tr = run(sym)
        except FileNotFoundError as e:
            print(f"{sym}: data file missing ({e}) — run where the CSVs live")
            continue
        yrs = pd.Series([r for _, r in tr],
                        index=[dt for dt, _ in tr])
        by_year = yrs.groupby(yrs.index.year).sum()
        print(f"\n{sym} per-year (sum of per-day P&L, {len(tr)} trade-days):")
        for y, v in by_year.items():
            print(f"  {y}: {v:+.1%}")
        six_filters(m_from_trades(tr, 2019, 2022),
                    m_from_trades(tr, 2023, 2026),
                    f"Intraday momentum (noise bands + VWAP stop) — {sym}")
    print("\nIF IT PASSES: still required before adoption — correlation of its "
          "daily P&L to the S1/S5 Nasdaq sleeve (<0.3), walk-forward windows, "
          "and a decay check (paper's sample ends 2024). See EDGE_HUNT_BRIEF.md.")
