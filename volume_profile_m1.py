"""
volume_profile_m1.py — Volume Profile strategy on 1-minute QQQ data.

Re-test of the volume profile approach (rejected on hourly data in FINDINGS.md)
using the M1 bars from qqq_1min_7y.csv (7 years, ~730k bars RTH-only).

A real volume profile at M1 resolution has ~390 bars/day vs ~7 on hourly.
This test resolves the data-limitation caveat noted in FINDINGS.md.

Signal (same logic as volume_profile_backtest.py — NO parameter changes):
  rolling 10-day M1 profile → VAL/POC/VAH
  long when price < VAL in uptrend; exit at POC or after 8 bars
OOS split: IN-sample 2019-21, OUT-of-sample 2022-23 (same as original test)
"""
import pandas as pd
import numpy as np
import pytz
import warnings
from datetime import date, timedelta
import yfinance as yf
warnings.filterwarnings("ignore")

eastern = pytz.timezone("US/Eastern")
START, END = "2019-01-01", "2023-12-31"
YEARS      = range(2019, 2024)
SLIP       = 0.0003    # same as original

print("Loading 1-min QQQ data...")
df = pd.read_csv("qqq_1min_7y.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.set_index("timestamp").tz_convert(eastern)
if "symbol" in df.columns:
    df = df[df["symbol"] == "QQQ"]
df = df[["open", "high", "low", "close", "volume"]].copy()
df.columns = ["Open", "High", "Low", "Close", "Volume"]
# RTH only: 9:30-16:00
df = df[(df.index.hour >= 9) & (df.index.hour < 16)]
df = df[~((df.index.hour == 9) & (df.index.minute < 30))]
df = df[(df.index.date >= pd.Timestamp(START).date()) &
        (df.index.date <= pd.Timestamp(END).date())]
df["Date"] = df["Date"] = df.index.date
print(f"  {len(df):,} RTH bars from {df.index[0].date()} to {df.index[-1].date()}")

# ── Daily trend filter (EMA50 > EMA200 on daily closes) ──
dc = df[df.index.hour == 15][["Close"]].copy()
dc.index = dc.index.date
dc = dc[~dc.index.duplicated(keep="last")]
ema50  = dc["Close"].ewm(span=50).mean()
ema200 = dc["Close"].ewm(span=200).mean()
df["EMA50"]  = df["Date"].map(ema50.to_dict())
df["EMA200"] = df["Date"].map(ema200.to_dict())

# ── VIX regime ──
vix = yf.download("^VIX", start=START, end=str(date.today()), progress=False)["Close"]
if isinstance(vix, pd.DataFrame): vix = vix.iloc[:, 0]
vix.index = pd.to_datetime(vix.index).tz_localize(None).normalize()
vma = vix.rolling(21).mean()
dts = pd.DatetimeIndex([pd.Timestamp(d) for d in sorted(df["Date"].unique())])
vix_by = vma.asof(dts)
vix_by.index = [t.date() for t in vix_by.index]
def vmult(d):
    v = vix_by.get(d, np.nan)
    return 1.0 if pd.isna(v) else (0.0 if v > 25 else (0.5 if v >= 20 else 1.0))

# ── Rolling 10-day volume profile at M1 resolution ──
print("Building rolling 10-day volume profiles (M1)...")
days = sorted(df["Date"].unique())
poc, vah, val = {}, {}, {}
N_BINS = 200   # 4× more bins than the hourly version (50 bins) for finer resolution

for k in range(10, len(days)):
    window = df[(df["Date"] >= days[k-10]) & (df["Date"] < days[k])]
    if len(window) < 100:
        continue
    lo, hi = window["Low"].min(), window["High"].max()
    if hi <= lo:
        continue
    bins = np.linspace(lo, hi, N_BINS)
    vol  = np.zeros(len(bins) - 1)
    for _, r in window.iterrows():
        c   = min(max(r["Close"], lo), hi)
        idx = min(int((c - lo) / (hi - lo) * (len(bins) - 1)), len(bins) - 2)
        vol[idx] += r["Volume"]
    poc_i = int(np.argmax(vol))
    poc[days[k]] = (bins[poc_i] + bins[poc_i + 1]) / 2
    # Value area: expand from POC until 70% of volume
    order = np.argsort(vol)[::-1]; cum = 0.0; tot = vol.sum(); sel = []
    for j in order:
        sel.append(j); cum += vol[j]
        if cum >= 0.70 * tot:
            break
    val[days[k]] = bins[min(sel)]
    vah[days[k]] = bins[max(sel) + 1]
    if k % 50 == 0:
        print(f"  {days[k]} ...", end="\r", flush=True)

df["POC"] = df["Date"].map(poc)
df["VAL"] = df["Date"].map(val)
df["VAH"] = df["Date"].map(vah)
print(f"\n  Profile built for {len(poc)} days")

# Signal: same as original — long below VAL in uptrend
df["below_val"] = (df["Close"] < df["VAL"]) & df["VAL"].notna()
df["uptrend"]   = df["EMA50"] > df["EMA200"]
df["VP_long"]   = (df["below_val"] & df["uptrend"]).astype(int)
df["VP_inv"]    = ((df["Close"] > df["VAH"]) & df["uptrend"]).astype(int)

print(f"  VP_long signals: {int(df['VP_long'].sum()):,}  "
      f"VP_inv signals: {int(df['VP_inv'].sum()):,}")


def run(sig, sl=0.015, rr=2.0, hold=8):
    """Same engine as volume_profile_backtest.py — NO parameter changes."""
    out = {}
    for Y in YEARS:
        cap = init = 10_000; in_t = False; entry = stop = tgt = sh = 0.0
        held = 0; cur = None; ds = cap; lock = False; dt = None
        for i in range(1, len(df)):
            if df.index[i].year != Y:
                continue
            d     = df.index[i].date()
            price = float(df["Close"].iloc[i])
            s     = int(df[sig].iloc[i - 1])
            vm    = vmult(df.index[i - 1].date())
            if d != cur:
                cur = d; ds = cap; lock = False
            if (cap - ds) / max(ds, 1) <= -0.05 or (cap - init) / init <= -0.10:
                lock = True
            if lock:
                continue
            if in_t:
                held += 1
                poc_val = df["POC"].iloc[i]
                tgt_hit = (price >= float(poc_val)
                           if not pd.isna(poc_val) else price >= tgt)
                if price <= stop or tgt_hit or held >= hold:
                    pnl = sh * (price - entry) - sh * (entry + price) * SLIP
                    cap += pnl; in_t = False
            elif s == 1 and vm > 0 and dt != d:
                in_t = True; dt = d; entry = price
                stop = price * (1 - sl); tgt = price * (1 + sl * rr)
                held = 0; sh = (cap * 0.005 * vm) / (price * sl)
        out[Y] = (cap - init) / init
    return out


print("\n" + "="*72)
print("VOLUME PROFILE on M1 DATA — QQQ 1-min (2019-2023)")
print("Same signal/params as volume_profile_backtest.py (hourly); only data changes")
print("="*72)
hdr = f"{'Variant':<30}" + "".join(f"{Y:>8}" for Y in YEARS)
hdr += f"{'avg':>8}{'IN 19-21':>9}{'OUT 22-23':>10}"
print(hdr); print("-" * 72)
for name, sig in [("VP mean-revert (below VAL)", "VP_long"),
                  ("INVERSE check (above VAH)",   "VP_inv")]:
    r = run(sig)
    avg = np.mean([r[Y] for Y in YEARS])
    IN  = np.mean([r[Y] for Y in (2019, 2020, 2021)])
    OUT = np.mean([r[Y] for Y in (2022, 2023)])
    row = f"{name:<30}" + "".join(f"{r[Y]:>+8.1%}" for Y in YEARS)
    row += f"{avg:>+8.1%}{IN:>+9.1%}{OUT:>+10.1%}"
    print(row)
print("-" * 72)
print("\nInterpretation:")
print("  Positive avg AND positive OUT = real edge → update FINDINGS.md to VALIDATED")
print("  Negative avg or OOS           = still no edge → confirm REJECTED in FINDINGS.md")
