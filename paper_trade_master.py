"""
Master Paper Trading System — FINAL CONFIG
5 strategies: S1 Asian Sweep, S2 Gold FVG, S3 Volume Momentum,
              S4 Multi-Sweep, S5 ORB 30-min

Backtest result: +278% over 7 years, -7.0% max DD, Sharpe 1.74, 1.52%/month
Simulates The5%ers $50k Bootcamp: 6% target, 6% max DD, no time limit

Run once per day after market close (4pm ET):
    python3 paper_trade_master.py
"""

import pandas as pd
import yfinance as yf
import pytz
from datetime import datetime, date
import os

# ── CONFIG — matches master_backtest.py final state ──
ACCOUNT_SIZE   = 50_000
PROFIT_TARGET  = 0.06     # The5%ers 6% target
MAX_DD         = 0.06     # 6% max DD
DAILY_LIMIT    = 0.05
LOG_FILE       = "/Users/colindayer/nas100_backtest/paper_trades.csv"
STATUS_FILE    = "/Users/colindayer/nas100_backtest/paper_status.csv"

# Final risk config (+ORB variant, no vol scaling, no TSMOM)
RISK_S1 = 0.0070
RISK_S2 = 0.0050
RISK_S3 = 0.0040   # per symbol
RISK_S4 = 0.0040   # per symbol
RISK_S5 = 0.0075   # ORB — bi-directional, 30-min range
STOP_S1 = 0.015;  RR_S1 = 3.0
STOP_S2 = 0.015;  RR_S2 = 3.0
STOP_S3 = 0.020
STOP_S4 = 0.015;  RR_S4 = 3.0

S3_SYMBOLS     = ["QQQ", "GLD", "GDX", "SLV", "USO"]
VOL_THRESHOLD  = 1.5
HOLD_BARS_S3   = 5

eastern = pytz.timezone("US/Eastern")
now_et  = datetime.now(eastern)
today   = now_et.date()

print(f"\n{'='*60}")
print(f"MASTER PAPER TRADER — {today}")
print(f"Simulating: The5%ers $50k Bootcamp (6% target, no time limit)")
print(f"{'='*60}\n")

# ── LOAD OR INIT STATUS ──
if os.path.exists(STATUS_FILE):
    status = pd.read_csv(STATUS_FILE, index_col=0).iloc[-1]
    capital        = float(status["capital"])
    peak_capital   = float(status["peak_capital"])
    start_capital  = float(status["start_capital"])
    days_running   = int(status["days_running"])
else:
    capital = peak_capital = start_capital = ACCOUNT_SIZE
    days_running = 0

total_ret = (capital - start_capital) / start_capital
cur_dd    = (capital - peak_capital)  / peak_capital

print(f"Account status:")
print(f"  Capital:      ${capital:,.2f}")
print(f"  Total return: {total_ret:+.2%} (target: +{PROFIT_TARGET:.0%})")
print(f"  Current DD:   {cur_dd:.2%}  (limit: -{MAX_DD:.0%})")
print(f"  Days running: {days_running}")
print(f"  Progress:     {min(total_ret/PROFIT_TARGET*100, 100):.1f}% to target\n")

if total_ret >= PROFIT_TARGET:
    print("🎉 PROFIT TARGET HIT — Challenge complete! Switch to funded account rules.")
    exit()

if cur_dd <= -MAX_DD:
    print("❌ MAX DRAWDOWN HIT — Stop trading. Reset or appeal.")
    exit()

# ── DOWNLOAD DATA ──
print("Downloading latest data...")
end_str   = str(today)
start_str = "2019-01-01"

# S3: Abnormal Volume (daily bars)
s3_signals = {}
raw_s3 = {}
for sym in S3_SYMBOLS:
    d = yf.download(sym, start=start_str, end=end_str,
                    interval="1d", progress=False, auto_adjust=True)
    d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    raw_s3[sym] = d

    c = d["Close"].squeeze()
    o = d["Open"].squeeze()
    v = d["Volume"].squeeze()
    vol_mean = v.rolling(66).mean().shift(1)
    vol_std  = v.rolling(66).std().shift(1)
    abnvol   = (v - vol_mean) / vol_std
    dayret   = (c - o) / o
    sig      = ((abnvol > VOL_THRESHOLD) & (dayret > 0.01))

    # Signal fires YESTERDAY → enter TODAY at open
    if len(sig) >= 2 and sig.iloc[-2]:
        s3_signals[sym] = {
            "entry_price": float(c.iloc[-1]),  # today's close as proxy
            "stop_price":  float(c.iloc[-1]) * (1 - STOP_S3),
            "shares":      (capital * RISK_S3) / (float(c.iloc[-1]) * STOP_S3),
            "abnvol":      float(abnvol.iloc[-2]),
            "dayret":      float(dayret.iloc[-2]),
        }

# VIX + SPY regime
vix_raw = yf.download("^VIX", start="2024-01-01", end=end_str, progress=False)
vix = vix_raw["Close"]
if isinstance(vix, pd.DataFrame): vix = vix.iloc[:, 0]
vix_ma21 = float(vix.rolling(21).mean().iloc[-1])

spy_raw = yf.download("SPY", start="2023-01-01", end=end_str, progress=False)
spy = spy_raw["Close"]
if isinstance(spy, pd.DataFrame): spy = spy.iloc[:, 0]
spy_ema50  = spy.ewm(span=50,  adjust=False).mean().iloc[-1]
spy_ema200 = spy.ewm(span=200, adjust=False).mean().iloc[-1]
spy_bull   = bool(spy_ema50 > spy_ema200)

if vix_ma21 > 25:   vix_regime = "HIGH — S1/S4 paused"
elif vix_ma21 >= 20: vix_regime = "MEDIUM — half size"
else:                vix_regime = "LOW — full size"

vix_mult = 0.0 if vix_ma21 > 25 else (0.5 if vix_ma21 >= 20 else 1.0)

print(f"\nRegime check:")
print(f"  VIX 21d avg: {vix_ma21:.1f} → {vix_regime}")
print(f"  SPY trend:   {'Golden cross ✅ (longs OK)' if spy_bull else 'Death cross ⚠️  (equity sweeps paused)'}")

# ── S3 SIGNALS ──
print(f"\n{'─'*60}")
print("S3: ABNORMAL VOLUME SIGNALS (act at tomorrow's open)")
print(f"{'─'*60}")

new_trades = []

if s3_signals:
    for sym, info in s3_signals.items():
        risk_amt = capital * RISK_S3
        pnl_target = info["shares"] * (info["entry_price"] * STOP_S3 * 3)
        print(f"\n  🚨 SIGNAL: {sym}")
        print(f"     Abnormal vol: {info['abnvol']:.2f}x std devs above baseline")
        print(f"     Day return:   {info['dayret']:+.2%}")
        print(f"     Action:       BUY {info['shares']:.1f} shares at market open tomorrow")
        print(f"     Entry ~price: ${info['entry_price']:.2f}")
        print(f"     Stop loss:    ${info['stop_price']:.2f} (-{STOP_S3:.0%})")
        print(f"     Hold:         {HOLD_BARS_S3} trading days then exit")
        print(f"     Risk amount:  ${risk_amt:.0f} ({RISK_S3:.1%} of capital)")
        new_trades.append({
            "date": str(today),
            "strategy": "S3",
            "symbol": sym,
            "action": "BUY",
            "price": round(info["entry_price"], 2),
            "shares": round(info["shares"], 2),
            "stop": round(info["stop_price"], 2),
            "hold_days": HOLD_BARS_S3,
            "risk_pct": RISK_S3,
            "status": "OPEN",
            "pnl": 0,
        })
else:
    print("  No S3 signals today.")

# ── S1/S2/S4 STATUS ──
equity_paused = not spy_bull or vix_mult == 0
print(f"\n{'─'*60}")
print(f"S1 (QQQ Asian Sweep):  {'⏸  PAUSED — regime filter' if equity_paused else '✅ Active — check hourly bars 2am-5am / 9am-12pm ET'}")
print(f"S2 (Gold London FVG):  {'✅ Active — check 2am-5am ET' if True else ''}")
print(f"S4 (Multi-sweep):      {'⏸  PAUSED — regime filter' if equity_paused else '✅ Active — check hourly bars 2am-5am / 9am-12pm ET'}")
print(f"\n  (S1/S2/S4 require hourly data — run this script hourly during session for live signals)")

# ── OPEN POSITIONS CHECK ──
print(f"\n{'─'*60}")
print("OPEN POSITIONS (manual tracking):")
if os.path.exists(LOG_FILE):
    log = pd.read_csv(LOG_FILE)
    open_pos = log[log["status"] == "OPEN"]
    if len(open_pos):
        for _, row in open_pos.iterrows():
            print(f"  {row['strategy']} {row['symbol']}: entered {row['date']} "
                  f"@ ${row['price']} | Stop: ${row['stop']} | "
                  f"Hold {row['hold_days']} days")
    else:
        print("  No open positions.")
else:
    print("  No trade log yet.")

# ── SAVE NEW TRADES ──
if new_trades:
    new_df = pd.DataFrame(new_trades)
    if os.path.exists(LOG_FILE):
        existing = pd.read_csv(LOG_FILE)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(LOG_FILE, index=False)
    print(f"\n✅ {len(new_trades)} signal(s) logged to {LOG_FILE}")

# ── SAVE STATUS ──
status_row = pd.DataFrame([{
    "date":          str(today),
    "capital":       capital,
    "peak_capital":  max(peak_capital, capital),
    "start_capital": start_capital,
    "total_ret":     total_ret,
    "current_dd":    cur_dd,
    "days_running":  days_running + 1,
    "vix_ma21":      round(vix_ma21, 2),
    "spy_bull":      spy_bull,
    "target_pct":    PROFIT_TARGET,
    "progress_pct":  round(min(total_ret / PROFIT_TARGET * 100, 100), 1),
}])

if os.path.exists(STATUS_FILE):
    existing = pd.read_csv(STATUS_FILE, index_col=0)
    combined = pd.concat([existing, status_row], ignore_index=True)
else:
    combined = status_row
combined.to_csv(STATUS_FILE)

print(f"\n{'='*60}")
print(f"DAILY SUMMARY")
print(f"{'='*60}")
print(f"  Progress to 6% target: {min(total_ret/PROFIT_TARGET*100,100):.1f}%")
print(f"  Capital remaining DD buffer: ${(capital * MAX_DD + (capital - peak_capital)):,.0f}")
print(f"  Status file: {STATUS_FILE}")
print(f"  Trade log:   {LOG_FILE}")
print(f"\nNext steps:")
print(f"  1. Execute any signals above at tomorrow's market open")
print(f"  2. Update closed trades manually in {LOG_FILE} (change status to CLOSED, add pnl)")
print(f"  3. Run this script again tomorrow after close")
print(f"  4. Update capital manually after each closed trade")
