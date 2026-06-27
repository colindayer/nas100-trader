"""
walkforward.py — Rolling walk-forward validation of the 4-strategy system.

Rolling window: TRAIN_MONTHS → TEST_MONTHS, stepping STEP_MONTHS each iteration.
Reports per-window Sharpe, return, max DD for each strategy and the combined system.
No parameter re-fitting — same signals as master_backtest.py, just evaluated on
non-overlapping test windows to confirm the OOS story holds across multiple eras.

Usage:
  python walkforward.py
  python walkforward.py --train 24 --test 6 --step 6
"""

import argparse
import warnings
from datetime import date, timedelta
import numpy as np
import pandas as pd
import pytz
import yfinance as yf

warnings.filterwarnings("ignore")
eastern = pytz.timezone("US/Eastern")

# ── Constants (match master_backtest.py exactly) ──────────────────────────────
RISK_S1 = 0.0070; STOP_S1 = 0.015; RR_S1 = 3.0
RISK_S2 = 0.0050; STOP_S2 = 0.015; RR_S2 = 3.0
RISK_S3 = 0.0040; STOP_S3 = 0.020; HOLD_S3 = 5
RISK_S4 = 0.0040; STOP_S4 = 0.015; RR_S4 = 3.0
RISK_S5 = 0.0075; STOP_S5 = 0.010; RR_S5 = 3.0
SLIP    = 0.0003


# ── Shared data load (once) ───────────────────────────────────────────────────
def load_qqq_hourly():
    print("Loading QQQ hourly data...")
    df = pd.read_csv("qqq_hourly_7y.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").tz_convert(eastern)
    if "symbol" in df.columns:
        df = df[df["symbol"] == "QQQ"]
    df = df[["open","high","low","close","volume"]].copy()
    df.columns = ["Open","High","Low","Close","Volume"]
    df["Date"] = df.index.date
    return df


def load_gld_hourly():
    print("Loading GLD hourly data...")
    try:
        df = pd.read_csv("gld_hourly_7y.csv")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").tz_convert(eastern)
        if "symbol" in df.columns:
            df = df[df["symbol"] == "GLD"]
        df = df[["open","high","low","close","volume"]].copy()
        df.columns = ["Open","High","Low","Close","Volume"]
        df["Date"] = df.index.date
        return df
    except FileNotFoundError:
        print("  gld_hourly_7y.csv not found; using yfinance daily fallback for GLD")
        return None


def load_qqq_1min():
    print("Loading QQQ 1-min data...")
    df = pd.read_csv("qqq_1min_7y.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").tz_convert(eastern)
    if "symbol" in df.columns:
        df = df[df["symbol"] == "QQQ"]
    df = df[["open","high","low","close","volume"]].copy()
    df.columns = ["Open","High","Low","Close","Volume"]
    df["Date"] = df.index.date
    return df


def load_vix():
    print("Loading VIX / regime data...")
    end = str(date.today())
    vix = yf.download("^VIX", start="2018-01-01", end=end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame): vix = vix.iloc[:,0]
    return vix


def build_qqq_signals(q: pd.DataFrame):
    """Build S1/S4 signals on QQQ hourly (same as master_backtest.py)."""
    def is_asian(idx): return idx.hour >= 18 or idx.hour < 2
    def sess_date(idx): return (idx + timedelta(days=1)).date() if idx.hour >= 18 else idx.date()

    q["Asian"]       = q.index.map(is_asian)
    q["SessionDate"] = q.index.map(sess_date)
    ab = q[q["Asian"]]
    q["AsianHigh"] = q["SessionDate"].map(ab.groupby("SessionDate")["High"].max())
    q["AsianLow"]  = q["SessionDate"].map(ab.groupby("SessionDate")["Low"].min())

    def in_sess(x):
        h, m = x.hour, x.minute
        return (2<=h<5) or (h==9 and m>=30) or (10<=h<12)
    q["InSession"] = q.index.map(in_sess)
    q["InLondon"]  = q.index.map(lambda x: 2 <= x.hour < 5)

    pc = q["Close"].shift(1)
    tr = pd.concat([q["High"]-q["Low"],(q["High"]-pc).abs(),(q["Low"]-pc).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    q["HighVol"] = atr > 1.5 * atr.rolling(200).mean()

    daily_close = q[q.index.hour == 16][["Close"]].copy()
    daily_close.index = daily_close.index.date
    daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
    ema50  = daily_close["Close"].ewm(span=50).mean()
    ema200 = daily_close["Close"].ewm(span=200).mean()
    q["DailyEMA50"]  = q["Date"].map(ema50.to_dict())
    q["DailyEMA200"] = q["Date"].map(ema200.to_dict())

    q["S1"] = (
        (q["Low"] < q["AsianLow"]) & (q["Close"] > q["AsianLow"]) &
        q["InSession"] & (q["Close"] > q["DailyEMA50"]) &
        ~q["HighVol"] & q["AsianLow"].notna()
    ).astype(int)

    q["S4"] = (
        (q["Low"] < q["AsianLow"]) & (q["Close"] > q["AsianLow"]) &
        q["InSession"] & (q["Close"] > q["DailyEMA50"]) &
        (q["DailyEMA50"] > q["DailyEMA200"]) &
        ~q["HighVol"] & q["AsianLow"].notna()
    ).astype(int)
    return q


def build_orb_signals(m1: pd.DataFrame):
    """Build S5 ORB signals on 1-min QQQ data."""
    m1["Date"] = m1.index.date
    daily_close = m1[(m1.index.hour == 15) & (m1.index.minute == 59)][["Close"]].copy()
    daily_close.index = daily_close.index.date
    daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
    ema200 = daily_close["Close"].rolling(200).mean()
    bull = daily_close["Close"] > ema200

    days = sorted(m1["Date"].unique())
    orb_high, orb_low, orb_normal = {}, {}, {}
    for d in days:
        day_bars = m1[m1["Date"] == d]
        first30  = day_bars.iloc[:30]
        if len(first30) < 15:
            continue
        oh = first30["High"].max(); ol = first30["Low"].min()
        orb_high[d] = oh; orb_low[d] = ol
        rng = (oh - ol) / first30["Close"].iloc[-1]
        orb_normal[d] = rng

    avg_rng_by_day = {}
    day_list = sorted(orb_normal.keys())
    for i, d in enumerate(day_list):
        if i < 5:
            avg_rng_by_day[d] = None
            continue
        recent = [orb_normal[day_list[j]] for j in range(max(0,i-20),i)]
        avg_rng_by_day[d] = np.mean(recent) if recent else None

    m1["ORB_High"]   = m1["Date"].map(orb_high)
    m1["ORB_Low"]    = m1["Date"].map(orb_low)
    m1["ORB_Normal"] = m1["Date"].map(lambda d: (
        avg_rng_by_day.get(d) is not None and
        orb_normal.get(d, 999) < avg_rng_by_day.get(d, 0) * 1.2
    ))
    m1["Bull200"] = m1["Date"].map(bull.to_dict()).fillna(False).astype(bool)

    entry_window = (m1.index.hour >= 10) & (m1.index.hour < 13)
    m1["S5L"] = (
        entry_window & m1["ORB_Normal"] & m1["Bull200"] &
        (m1["Close"] > m1["ORB_High"])
    ).astype(int)
    m1["S5S"] = (
        entry_window & m1["ORB_Normal"] & ~m1["Bull200"] &
        (m1["Close"] < m1["ORB_Low"])
    ).astype(int)
    return m1


# ── Backtest engines ──────────────────────────────────────────────────────────
def run_intraday(df: pd.DataFrame, sig: str, risk: float, sl: float, rr: float,
                 vix: pd.Series, short: bool = False) -> list:
    """Returns list of (exit_date, pnl) for trade closure events."""
    rows = []
    in_t = False; entry = stop = tgt = sh = 0.0; day_traded = None
    cap = 10_000; ds = cap; cur_date = None; lock = False

    def vmult(d):
        vix_ma = vix.rolling(21).mean().asof(pd.Timestamp(d))
        return 1.0 if pd.isna(vix_ma) else (0.0 if vix_ma > 25 else (0.5 if vix_ma >= 20 else 1.0))

    for i in range(1, len(df)):
        d     = df.index[i].date()
        price = float(df["Close"].iloc[i])
        s     = int(df[sig].iloc[i-1])
        vm    = vmult(d)

        if d != cur_date: cur_date = d; ds = cap; lock = False
        if (cap - ds) / max(ds, 1) <= -0.05 or (cap - 10_000) / 10_000 <= -0.10:
            lock = True
        if lock: continue

        if in_t:
            pnl = None
            if not short:
                if price <= stop: pnl = sh*(stop-entry) - sh*(entry+stop)*SLIP
                elif price >= tgt: pnl = sh*(tgt-entry)  - sh*(entry+tgt)*SLIP
            else:
                if price >= stop: pnl = sh*(entry-stop)  - sh*(entry+stop)*SLIP
                elif price <= tgt: pnl = sh*(entry-tgt)  - sh*(entry+tgt)*SLIP
            if pnl is not None:
                cap += pnl; rows.append((d, pnl)); in_t = False
        elif s == 1 and vm > 0 and day_traded != d:
            in_t = True; day_traded = d; entry = price
            if not short: stop = price*(1-sl); tgt = price*(1+sl*rr)
            else:         stop = price*(1+sl); tgt = price*(1-sl*rr)
            sh = (cap * risk * vm) / (price * sl)
    return rows


# ── Walk-forward engine ───────────────────────────────────────────────────────
def walk_forward(q, m1, vix, train_mo, test_mo, step_mo) -> list:
    FULL_START = pd.Timestamp("2019-01-01", tz=eastern)
    FULL_END   = pd.Timestamp("2024-12-31", tz=eastern)
    results = []

    train_start = FULL_START
    while True:
        train_end = train_start + pd.DateOffset(months=train_mo)
        test_end  = train_end   + pd.DateOffset(months=test_mo)
        if test_end > FULL_END:
            break

        label = (f"{train_start.strftime('%Y-%m')}→{train_end.strftime('%Y-%m')}"
                 f" TEST:{train_end.strftime('%Y-%m')}→{test_end.strftime('%Y-%m')}")

        # Slice test window
        q_test  = q[(q.index  >= train_end) & (q.index  < test_end)]
        m1_test = m1[(m1.index >= train_end) & (m1.index < test_end)]

        if len(q_test) < 50 or len(m1_test) < 500:
            train_start += pd.DateOffset(months=step_mo); continue

        def kpi(trades):
            if not trades: return 0.0, 0.0, 0.0
            cap = 10_000
            by_day = {}
            for d, p in trades:
                ts = pd.Timestamp(d)
                by_day[ts] = by_day.get(ts, 0.0) + p
            eq = pd.Series(by_day).sort_index().cumsum() + cap
            rets = eq.pct_change().fillna(0)
            ret  = (eq.iloc[-1]/cap - 1)
            vol  = rets.std() * np.sqrt(252)
            sh   = (rets.mean() * 252) / vol if vol > 0 else 0.0
            dd   = ((eq - eq.cummax()) / eq.cummax()).min()
            return ret, sh, dd

        t_s1 = run_intraday(q_test,  "S1", RISK_S1, STOP_S1, RR_S1, vix)
        t_s4 = run_intraday(q_test,  "S4", RISK_S4, STOP_S4, RR_S4, vix)
        t_s5l = run_intraday(m1_test, "S5L", RISK_S5, STOP_S5, RR_S5, vix)
        t_s5s = run_intraday(m1_test, "S5S", RISK_S5*0.6, STOP_S5, RR_S5, vix, short=True)
        all_t = t_s1 + t_s4 + t_s5l + t_s5s

        r_s1,  sh_s1,  dd_s1  = kpi(t_s1)
        r_s4,  sh_s4,  dd_s4  = kpi(t_s4)
        r_s5l, sh_s5l, dd_s5l = kpi(t_s5l)
        r_cmb, sh_cmb, dd_cmb = kpi(all_t)

        results.append(dict(
            window=label,
            n_s1=len(t_s1), ret_s1=r_s1, sharpe_s1=sh_s1, dd_s1=dd_s1,
            n_s4=len(t_s4), ret_s4=r_s4, sharpe_s4=sh_s4, dd_s4=dd_s4,
            n_s5l=len(t_s5l), ret_s5l=r_s5l, sharpe_s5l=sh_s5l, dd_s5l=dd_s5l,
            n_cmb=len(all_t), ret_cmb=r_cmb, sharpe_cmb=sh_cmb, dd_cmb=dd_cmb,
        ))
        print(f"  {label} | combined ret={r_cmb:+.1%} sharpe={sh_cmb:.2f} dd={dd_cmb:.1%}")
        train_start += pd.DateOffset(months=step_mo)
    return results


# ── Main ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--train", type=int, default=24, help="Train window in months (default 24)")
parser.add_argument("--test",  type=int, default=6,  help="Test window in months  (default 6)")
parser.add_argument("--step",  type=int, default=6,  help="Step size in months    (default 6)")
args = parser.parse_args()

q   = load_qqq_hourly()
m1  = load_qqq_1min()
vix = load_vix()

print("Building signals...")
q  = build_qqq_signals(q)
m1 = build_orb_signals(m1)

print(f"\nWalk-forward: {args.train}m train / {args.test}m test / {args.step}m step\n")
results = walk_forward(q, m1, vix, args.train, args.test, args.step)

if not results:
    print("No complete windows found — extend the data range.")
    import sys; sys.exit(1)

df_r = pd.DataFrame(results)
print("\n" + "="*100)
print(f"WALK-FORWARD RESULTS ({args.train}m/{args.test}m/{args.step}m) — Combined S1+S4+S5")
print("="*100)
print(f"{'Window':<55} {'Ret':>7} {'Sharpe':>7} {'DD':>7} {'Trades':>7}")
print("-"*100)
for _, row in df_r.iterrows():
    marker = "✓" if row["ret_cmb"] > 0 else "✗"
    print(f"{row['window']:<55} {row['ret_cmb']:>+7.1%} {row['sharpe_cmb']:>7.2f} "
          f"{row['dd_cmb']:>7.1%} {int(row['n_cmb']):>7}  {marker}")
print("-"*100)
pos = (df_r["ret_cmb"] > 0).sum()
n   = len(df_r)
avg_ret    = df_r["ret_cmb"].mean()
avg_sharpe = df_r["sharpe_cmb"].mean()
avg_dd     = df_r["dd_cmb"].mean()
print(f"{'Avg / % positive windows':<55} {avg_ret:>+7.1%} {avg_sharpe:>7.2f} "
      f"{avg_dd:>7.1%} {'':>7}  {pos}/{n} ({100*pos/n:.0f}%)")
print("="*100)

print(f"\nS1 breakdown by window:")
print(f"  avg ret {df_r['ret_s1'].mean():+.1%}, avg sharpe {df_r['sharpe_s1'].mean():.2f}, "
      f"positive {(df_r['ret_s1']>0).sum()}/{n} windows")
print(f"S4 breakdown by window:")
print(f"  avg ret {df_r['ret_s4'].mean():+.1%}, avg sharpe {df_r['sharpe_s4'].mean():.2f}, "
      f"positive {(df_r['ret_s4']>0).sum()}/{n} windows")
print(f"S5L breakdown by window:")
print(f"  avg ret {df_r['ret_s5l'].mean():+.1%}, avg sharpe {df_r['sharpe_s5l'].mean():.2f}, "
      f"positive {(df_r['ret_s5l']>0).sum()}/{n} windows")
