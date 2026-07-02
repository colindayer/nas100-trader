"""
verify_liveness.py — PROVE the strategy logic can actually fire.

"Session complete" only proves the bot ran. This replays REAL recent history
through each strategy's exact entry condition (copied from live_trader.py) and
reports: how many signals it WOULD have fired + the date of the most recent one.

  • Signals in the window  → the code path is provably alive.
  • Last-signal date recent → you're in a normal quiet patch, not broken.
  • 0 signals over months   → RED FLAG: investigate before trusting it live.

Note: GEX cache stops 2023, so S1/S4 here count the PRICE-STRUCTURE signal
(sweep+VWAP+EMA+session). Live additionally requires negative GEX, so live fires
are a subset of these. The point is to prove the price logic is alive.
"""
import pandas as pd, numpy as np, pytz, warnings, sys
from datetime import timedelta
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
eastern = pytz.timezone("US/Eastern")

WINDOW_DAYS = 180   # "recent" lookback to report


def load_hourly(sym):
    df = pd.read_csv(f"{sym.lower()}_hourly_7y.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").tz_convert(eastern)
    if "symbol" in df: df = df[df["symbol"] == sym]
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def asian_cols(data):
    data = data.copy()
    data["Date"] = data.index.date
    data["Asian"] = data.index.map(lambda i: i.hour >= 18 or i.hour < 2)
    data["SessionDate"] = data.index.map(
        lambda i: (i + timedelta(days=1)).date() if i.hour >= 18 else i.date())
    ab = data[data["Asian"]]
    data["AsianHigh"] = data["SessionDate"].map(ab.groupby("SessionDate")["High"].max())
    data["AsianLow"]  = data["SessionDate"].map(ab.groupby("SessionDate")["Low"].min())
    dc = data[data.index.hour == 16][["Close"]].copy(); dc.index = dc.index.date
    dc = dc[~dc.index.duplicated(keep="last")]
    data["EMA50"]  = data["Date"].map(dc["Close"].ewm(span=50).mean().to_dict())
    data["EMA200"] = data["Date"].map(dc["Close"].ewm(span=200).mean().to_dict())
    pc = data["Close"].shift(1)
    tr = pd.concat([data["High"]-data["Low"], (data["High"]-pc).abs(),
                    (data["Low"]-pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    data["HighVol"] = atr > 1.5 * atr.rolling(200).mean()
    return data


def vwap(data):
    tp = (data["High"]+data["Low"]+data["Close"])/3
    out=[]; ct=cv=0.; pd_=None
    for i in range(len(data)):
        d = data["Date"].iloc[i]
        if d != pd_: ct=cv=0.; pd_=d
        if data["Volume"].iloc[i] > 0:
            ct += tp.iloc[i]*data["Volume"].iloc[i]; cv += data["Volume"].iloc[i]
        out.append(ct/cv if cv > 0 else np.nan)
    return pd.Series(out, index=data.index)


def s1_signals(data):
    data = asian_cols(data); data["VWAP"] = vwap(data)
    data["InSession"] = data.index.map(lambda x: (2<=x.hour<5) or (9<=x.hour<12))
    sweep = (data["Low"] < data["AsianLow"]) & (data["Close"] > data["AsianLow"])
    return (sweep & data["InSession"] & (data["Close"] > data["VWAP"]) &
            (data["Close"] > data["EMA50"]) & ~data["HighVol"] & data["AsianLow"].notna())


def s4_signals(data):
    data = asian_cols(data)
    data["InSession"] = data.index.map(
        lambda x: (2<=x.hour<5) or (x.hour==9 and x.minute>=30) or (10<=x.hour<12))
    sweep = (data["Low"] < data["AsianLow"]) & (data["Close"] > data["AsianLow"])
    return (sweep & data["InSession"] & (data["Close"] > data["EMA50"]) &
            (data["EMA50"] > data["EMA200"]) & ~data["HighVol"] & data["AsianLow"].notna())


def s3_signals(sym):
    d = load_hourly(sym)
    day = d["Close"].resample("1D").last().to_frame("Close")
    day["Open"] = d["Open"].resample("1D").first()
    day["Vol"]  = d["Volume"].resample("1D").sum()
    day = day.dropna()
    vm = day["Vol"].rolling(66).mean().shift(1); vs = day["Vol"].rolling(66).std().shift(1)
    abnvol = (day["Vol"]-vm)/vs; dayret = (day["Close"]-day["Open"])/day["Open"]
    return pd.Series((abnvol > 1.5) & (dayret > 0.01), index=day.index)


def s5_signals(data):
    data = data.copy(); data["Date"] = data.index.date
    sig = pd.Series(False, index=data.index)
    for d, day in data.groupby("Date"):
        orb = day[day.index.hour == 9]
        if len(orb) == 0: continue
        oh, ol, ov = float(orb["High"].iloc[0]), float(orb["Low"].iloc[0]), float(orb["Volume"].iloc[0])
        win = day[(day.index.hour >= 10) & (day.index.hour <= 13)]
        for ts, bar in win.iterrows():
            if (bar["Close"] > oh or bar["Close"] < ol) and bar["Volume"] > ov*0.6:
                sig[ts] = True
    return sig


def report(name, sig, asset):
    if getattr(sig.index, "tz", None) is not None:
        sig = sig.copy(); sig.index = sig.index.tz_localize(None)
    end = sig.index.max()
    cutoff = end - pd.Timedelta(days=WINDOW_DAYS)
    recent = sig[sig.index >= cutoff]
    total = int(sig.sum()); rec = int(recent.sum())
    fired = sig[sig]
    last = fired.index.max().date() if len(fired) else "NEVER"
    flag = "🔴 0 in window — INVESTIGATE" if rec == 0 else "🟢 alive"
    print(f"  {name:<22} {asset:<5} | last {WINDOW_DAYS}d: {rec:>3} signals | "
          f"7y total: {total:>4} | last: {last}  {flag}")


def main():
    print(f"REPLAY LIVENESS TEST — signals each strategy WOULD fire "
          f"(last {WINDOW_DAYS} days + 7y)\n")
    try:
        qqq = load_hourly("QQQ")
    except FileNotFoundError:
        print("  qqq_hourly_7y.csv missing — on the VPS create it from the MT5 "
              "bridge:\n  python fetch_mt5_history.py --symbols US100 --alias qqq")
        return
    report("S1 Asian sweep",   s1_signals(qqq), "QQQ")
    report("S4 multi-sweep",   s4_signals(qqq), "QQQ")
    try:
        spy = load_hourly("SPY")
        report("S4 multi-sweep", s4_signals(spy), "SPY")
    except FileNotFoundError:
        print("  S4 SPY: spy_hourly_7y.csv missing — skipped")
    report("S5 ORB breakout",  s5_signals(qqq), "QQQ")
    for s in ["QQQ", "GLD", "GDX", "SLV", "USO"]:
        try: report("S3 abnormal-vol", s3_signals(s), s)
        except FileNotFoundError: print(f"  S3 {s}: no data file — skipped")
        except Exception as e: print(f"  S3 {s}: data err ({e})")
    print("\nNote: S1/S4 counts are PRE-GEX (live also needs negative GEX → fewer). "
          "A recent non-zero count proves the price logic is alive and firing.")


if __name__ == "__main__":
    main()
