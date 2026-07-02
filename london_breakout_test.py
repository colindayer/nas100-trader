"""
london_breakout_test.py — gauntlet test of the "Asian range London Breakout"
(video rules, faithfully implemented):

  01 Mark Asian session high/low            (00:00–06:59 UTC here)
  02 Filter: skip range >40 pips or <15 pips (sweet spot 20–35)
  03 Entry: Buy Stop 5 pips above Asian high + Sell Stop 5 pips below Asian
     low, active 07:00–10:59 UTC (London morning)
  04 Stop: at the opposite Asian extreme, tightened to max 20 pips from entry
  05 TP at 1:1 risk-reward
  06 OCO (first fill cancels the other), force-close 11:00 UTC

Data: the MT5 bridge CSVs — run on the VPS first:
    python fetch_mt5_history.py --symbols EURUSD GBPUSD --years 6
    python london_breakout_test.py --symbols EURUSD GBPUSD

HONESTY NOTES
- Hourly bars can't see the intrabar path. When one bar touches BOTH the TP
  and SL we count the PESSIMISTIC outcome (SL first) as primary and report the
  optimistic bound alongside — truth is in between. Bars that would trigger
  BOTH pending orders are skipped (counted as 'ambiguous').
- Costs: 1.2 pips round trip (spread+slip on a raw-spread CFD account).
- % returns assume 0.5% account risk per trade (R-multiples × 0.5%).
- NOTE this is the ANTI-S1: it trades WITH the Asian-range break; our
  validated S1 fades it. Both can't be right on the same instrument/session —
  a pass here on US100 would be suspicious; the video pitches it for FX majors.
"""
import argparse
import sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SPREAD_PIPS = 1.2
BUF_PIPS    = 5.0
RANGE_MIN, RANGE_MAX = 15.0, 40.0
MAX_STOP_PIPS = 20.0
RISK_PCT   = 0.005          # 0.5% of account risked per trade
ASIA = (0, 7)               # 00:00–06:59 UTC
WIN  = (7, 11)              # entry window 07:00–10:59 UTC; close at 11:00


def pip_size(sym):
    return 0.01 if "JPY" in sym.upper() else 0.0001


def load(sym):
    df = pd.read_csv(f"{sym.lower()}_hourly_mt5.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp").sort_index()


def run(sym):
    df = load(sym)
    pip = pip_size(sym)
    trades, amb = [], 0
    for day, d in df.groupby(df.index.date):
        asian = d[(d.index.hour >= ASIA[0]) & (d.index.hour < ASIA[1])]
        win = d[(d.index.hour >= WIN[0]) & (d.index.hour < WIN[1])]
        closebar = d[d.index.hour == WIN[1]]
        if len(asian) < 5 or len(win) == 0:
            continue
        ah, al = float(asian["high"].max()), float(asian["low"].min())
        rng = (ah - al) / pip
        if not (RANGE_MIN <= rng <= RANGE_MAX):
            continue
        buy_lvl, sell_lvl = ah + BUF_PIPS * pip, al - BUF_PIPS * pip

        pos, entry, sl, tp = 0, 0.0, 0.0, 0.0
        res_pess = res_opt = None
        for ts, bar in win.iterrows():
            hi, lo, op = float(bar["high"]), float(bar["low"]), float(bar["open"])
            if pos == 0:
                hit_buy, hit_sell = hi >= buy_lvl, lo <= sell_lvl
                if hit_buy and hit_sell:
                    amb += 1
                    break                       # can't order the touches — skip day
                if hit_buy or hit_sell:
                    pos = 1 if hit_buy else -1
                    entry = max(op, buy_lvl) if pos == 1 else min(op, sell_lvl)
                    stop_d = min((entry - al) if pos == 1 else (ah - entry),
                                 MAX_STOP_PIPS * pip)
                    sl = entry - pos * stop_d
                    tp = entry + pos * stop_d
                    # same-bar exit check (post-entry path unknown)
                    hit_sl = lo <= sl if pos == 1 else hi >= sl
                    hit_tp = hi >= tp if pos == 1 else lo <= tp
                    if hit_sl or hit_tp:
                        res_pess = -1.0 if hit_sl else 1.0
                        res_opt = 1.0 if hit_tp else -1.0
                        break
                continue
            hit_sl = lo <= sl if pos == 1 else hi >= sl
            hit_tp = hi >= tp if pos == 1 else lo <= tp
            if hit_sl or hit_tp:
                res_pess = -1.0 if hit_sl else 1.0
                res_opt = 1.0 if hit_tp else -1.0
                break
        if pos != 0 and res_pess is None:       # time exit at 11:00 UTC
            px = float(closebar["open"].iloc[0]) if len(closebar) else float(win["close"].iloc[-1])
            stop_d = abs(entry - sl)
            r = pos * (px - entry) / stop_d
            res_pess = res_opt = r
        if pos != 0:
            cost_r = (SPREAD_PIPS * pip) / abs(entry - sl)
            trades.append((pd.Timestamp(day), res_pess - cost_r, res_opt - cost_r))
    return trades, amb


def stats(rets):
    t = pd.Series(rets)
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["EURUSD", "GBPUSD"])
    args = ap.parse_args()
    for sym in args.symbols:
        try:
            trades, amb = run(sym)
        except FileNotFoundError:
            print(f"{sym}: missing {sym.lower()}_hourly_mt5.csv — run "
                  f"fetch_mt5_history.py --symbols {sym} first")
            continue
        if not trades:
            print(f"{sym}: no qualifying days (range filter) — check data")
            continue
        dts = [d for d, _, _ in trades]
        split = dts[0] + (dts[-1] - dts[0]) * 0.6          # 60/40 IS/OOS
        for label, idx in (("PESSIMISTIC (primary)", 1), ("optimistic bound", 2)):
            IS  = stats([t[idx] * RISK_PCT for t in trades if t[0] <= split])
            OOS = stats([t[idx] * RISK_PCT for t in trades if t[0] > split])
            six_filters(IS, OOS, f"London Breakout — {sym} [{label}]")
        yrs = (dts[-1] - dts[0]).days / 365.25
        print(f"  {len(trades)} trades in {yrs:.1f}y (~{len(trades)/yrs:.0f}/yr), "
              f"{amb} ambiguous days skipped")
    print("\nVERDICT RULE: adopt ONLY if the PESSIMISTIC line passes all six on "
          "BOTH symbols, plus corr-to-book < 0.3. If only the optimistic bound "
          "passes, re-test on M15 data before believing it.")
