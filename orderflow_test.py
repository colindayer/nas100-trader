"""
orderflow_test.py — Build + gauntlet-test the two QuantFlow-style concepts we
DON'T already have, on our own QQQ 15-min data, honestly:

  Model C  ORB break-RETEST   : opening range (9:30-10:00), wait for breakout,
                                then a retest hold of the OR high, enter long.
  Model B  Value-area retest  : build PRIOR-day volume profile (POC/VAH/VAL),
                                long when price breaks above prior VAH & retests.

Same rules as everything else: costs on, IS 2019-22 / OOS 2023-26, six filters.
We also compare RETURN + Sharpe to judge "do they beat what we have?" honestly.
NOTE: both are intraday-Nasdaq breakout family → expect them CORRELATED to S1/S5,
so even a pass is a weak diversifier. We report that plainly.
"""
import pandas as pd, numpy as np, pytz, warnings
warnings.filterwarnings("ignore")
eastern = pytz.timezone("US/Eastern")
SLIP, RR = 0.0004, 2.0

df = pd.read_csv("qqq_15min_7y.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.set_index("timestamp").tz_convert(eastern)
df = df[df["symbol"] == "QQQ"][["open","high","low","close","volume"]]
df.columns = ["Open","High","Low","Close","Volume"]
df = df[(df.index.hour >= 9) & (df.index.hour < 16)]   # RTH
df["Date"] = df.index.date
df["t"] = df.index.hour * 60 + df.index.minute


def value_area(day_df, bins=30):
    """POC / VAH / VAL from a day's 15-min bars (volume-by-price, 70% area)."""
    lo, hi = day_df["Low"].min(), day_df["High"].max()
    if hi <= lo: return None
    edges = np.linspace(lo, hi, bins + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    vol = np.zeros(bins)
    for _, r in day_df.iterrows():
        b = min(int((r["Close"] - lo) / (hi - lo) * bins), bins - 1)
        vol[b] += r["Volume"]
    poc_i = int(vol.argmax()); total = vol.sum()
    lo_i = hi_i = poc_i; acc = vol[poc_i]
    while acc < 0.70 * total and (lo_i > 0 or hi_i < bins - 1):
        down = vol[lo_i - 1] if lo_i > 0 else -1
        up = vol[hi_i + 1] if hi_i < bins - 1 else -1
        if up >= down: hi_i += 1; acc += vol[hi_i]
        else: lo_i -= 1; acc += vol[lo_i]
    return dict(poc=mids[poc_i], vah=mids[hi_i], val=mids[lo_i])


def run_orb_retest(data):
    trades = []
    for d, g in data.groupby("Date"):
        orb = g[(g["t"] >= 570) & (g["t"] < 600)]        # 9:30-10:00
        if len(orb) < 2: continue
        orh, orl = orb["High"].max(), orb["Low"].min()
        post = g[g["t"] >= 600]
        armed = False; entry = stop = tgt = None
        for _, r in post.iterrows():
            if entry is None:
                if not armed and r["Close"] > orh: armed = True
                elif armed and r["Low"] <= orh and r["Close"] > orh:
                    entry = r["Close"]; stop = orl; tgt = entry + RR*(entry-orl)
            else:
                if r["Low"] <= stop: trades.append((d, -(entry-stop)/entry - SLIP)); entry=None; break
                if r["High"] >= tgt: trades.append((d, (tgt-entry)/entry - SLIP)); entry=None; break
        if entry is not None:
            last = post["Close"].iloc[-1]; trades.append((d, (last-entry)/entry - SLIP))
    return trades


def run_value_area(data):
    days = sorted(data["Date"].unique())
    profiles = {d: value_area(data[data["Date"] == d]) for d in days}
    trades = []
    for i in range(1, len(days)):
        d, pv = days[i], profiles[days[i-1]]
        if pv is None: continue
        g = data[data["Date"] == d]; vah, val = pv["vah"], pv["val"]
        armed = False; entry = stop = tgt = None
        for _, r in g.iterrows():
            if entry is None:
                if not armed and r["Close"] > vah: armed = True
                elif armed and r["Low"] <= vah and r["Close"] > vah:
                    entry = r["Close"]; stop = val; tgt = entry + RR*(entry-val)
            else:
                if r["Low"] <= stop: trades.append((d, -(entry-stop)/entry - SLIP)); entry=None; break
                if r["High"] >= tgt: trades.append((d, (tgt-entry)/entry - SLIP)); entry=None; break
        if entry is not None:
            last = g["Close"].iloc[-1]; trades.append((d, (last-entry)/entry - SLIP))
    return trades


def stats(trades, lo, hi):
    sel = [r for (d, r) in trades if lo <= d.year <= hi]
    t = pd.Series(sel)
    if len(t) == 0: return dict(n=0, wr=0, ret=0, sharpe=0, dd=0)
    eq = (1+t).cumprod()
    return dict(n=len(t), wr=(t>0).mean(), ret=eq.iloc[-1]-1,
                sharpe=t.mean()/t.std()*np.sqrt(len(t)/ (hi-lo+1)) if t.std()>0 else 0,
                dd=(eq/eq.cummax()-1).min())


def gauntlet(name, trades):
    IS, OOS = stats(trades, 2019, 2022), stats(trades, 2023, 2026)
    print(f"\n{'='*60}\n{name}")
    for lab, m in [("IS  2019-22", IS), ("OOS 2023-26", OOS)]:
        print(f"  {lab}: n={m['n']:3d} wr={m['wr']:.0%} ret={m['ret']:+.1%} "
              f"Sharpe~{m['sharpe']:.2f} DD={m['dd']:.1%}")
    checks = {
        "OOS Sharpe>0.5": OOS["sharpe"] > 0.5, "maxDD>-35%": OOS["dd"] > -0.35,
        "OOS Sharpe<2.5": OOS["sharpe"] < 2.5,
        "not overfit": OOS["sharpe"] <= IS["sharpe"]*1.3+0.5,
        ">=30 trades": OOS["n"] >= 30, "IS Sharpe>0": IS["sharpe"] > 0,
    }
    for k, v in checks.items(): print(f"    [{'PASS' if v else 'FAIL'}] {k}")
    print(f"  >>> {'PASSES' if all(checks.values()) else 'REJECTED'}")


gauntlet("Model C — ORB break-RETEST (QQQ 15m)", run_orb_retest(df))
gauntlet("Model B — Value-area break-retest (prior-day VAH)", run_value_area(df))
print("\nReminder: both are intraday-Nasdaq breakout family — even a pass is")
print("CORRELATED to your S1/S5, so it adds little diversification.")
