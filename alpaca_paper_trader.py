"""
Automated Paper Trader — Alpaca Paper Trading Account
Runs S3 (Abnormal Volume) signals automatically — no manual execution needed.
Alpaca paper trading = fake money, real market prices, real order execution simulation.

Schedule: run once daily after 4pm ET
    python3 alpaca_paper_trader.py

Or automate with cron (runs automatically every day):
    crontab -e
    0 21 * * 1-5 cd /Users/colindayer/nas100_backtest && python3 alpaca_paper_trader.py
    (21:00 UTC = 5pm ET — after market close)
"""

import yfinance as yf
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import pytz

API_KEY    = "PKXGY4RL3FZEUSLDRREY2UMTJK"
SECRET_KEY = "3w1L7ymf6Pii5z2XrM1FjhFYvb96k6xm5ejrKeDt1w1W"

# Paper trading clients
trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
data    = StockHistoricalDataClient(API_KEY, SECRET_KEY)

SYMBOLS        = ["QQQ", "GLD", "GDX", "SLV", "USO"]
VOL_THRESHOLD  = 1.5
PRICE_THRESHOLD = 0.01
HOLD_DAYS      = 5
STOP_PCT       = 0.02
ACCOUNT_SIZE   = 50_000   # simulated — Alpaca paper starts at $100k by default
RISK_PER_SYM   = 0.0040   # 0.4% per symbol (equal weight across 5)
PROFIT_TARGET  = 0.06     # The5%ers 6% target
DD_LIMIT       = 0.06

eastern = pytz.timezone("US/Eastern")
today   = datetime.now(eastern).date()

print(f"\n{'='*55}")
print(f"ALPACA PAPER TRADER — S3 Volume Momentum — {today}")
print(f"{'='*55}\n")

# ── ACCOUNT STATUS ──
account = trading.get_account()
equity  = float(account.equity)
cash    = float(account.cash)
start_eq = ACCOUNT_SIZE  # track from when you started

print(f"Account equity: ${equity:,.2f}")
print(f"Cash available: ${cash:,.2f}")

# ── CHECK OPEN POSITIONS ──
positions = trading.get_all_positions()
open_syms = {p.symbol: p for p in positions}
print(f"Open positions: {list(open_syms.keys()) if open_syms else 'None'}")

# ── CLOSE POSITIONS HELD >= HOLD_DAYS ──
orders_req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50)
for sym, pos in list(open_syms.items()):
    # Check when position was opened via orders
    try:
        filled_orders = trading.get_orders(filter=GetOrdersRequest(
            status=QueryOrderStatus.CLOSED, symbols=[sym], limit=5))
        buy_orders = [o for o in filled_orders
                     if o.side == OrderSide.BUY and o.filled_at is not None]
        if buy_orders:
            filled_at = buy_orders[-1].filled_at
            if filled_at.tzinfo is None:
                filled_at = pytz.utc.localize(filled_at)
            days_held = (datetime.now(pytz.utc) - filled_at).days
            entry_price = float(buy_orders[-1].filled_avg_price)
            current_price = float(pos.current_price)
            pnl_pct = (current_price - entry_price) / entry_price

            print(f"\n  {sym}: held {days_held} days, P&L {pnl_pct:+.2%}")

            hit_stop   = pnl_pct <= -STOP_PCT
            hit_target = days_held >= HOLD_DAYS

            if hit_stop or hit_target:
                reason = "STOP HIT" if hit_stop else f"{HOLD_DAYS}-DAY EXIT"
                print(f"  → CLOSING {sym} ({reason})")
                order = trading.submit_order(MarketOrderRequest(
                    symbol=sym,
                    qty=abs(float(pos.qty)),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                ))
                print(f"  → Order submitted: {order.id}")
                del open_syms[sym]
    except Exception as e:
        print(f"  {sym}: could not check hold period — {e}")

# ── VIX REGIME CHECK ──
end_str   = str(today)
start_str = str(today - timedelta(days=60))
vix = yf.download("^VIX", start=start_str, end=end_str, progress=False)["Close"]
if isinstance(vix, pd.DataFrame): vix = vix.iloc[:,0]
vix_ma21 = float(vix.rolling(21).mean().iloc[-1])

spy = yf.download("SPY", start="2023-01-01", end=end_str, progress=False)["Close"]
if isinstance(spy, pd.DataFrame): spy = spy.iloc[:,0]
spy_bull = bool(spy.ewm(span=50,adjust=False).mean().iloc[-1] >
                spy.ewm(span=200,adjust=False).mean().iloc[-1])

print(f"\nRegime: VIX 21d={vix_ma21:.1f} | SPY {'Golden ✅' if spy_bull else 'Death ⚠️'} cross")

if vix_ma21 > 25:
    print("❌ VIX > 25 — no new trades today")
    exit()

size_mult = 0.5 if vix_ma21 >= 20 else 1.0

# ── S3 SIGNAL CHECK ──
print(f"\nChecking S3 signals...")
signals = []

for sym in SYMBOLS:
    if sym in open_syms:
        print(f"  {sym}: already in position — skip")
        continue

    d = yf.download(sym, start=str(today - timedelta(days=120)),
                    end=end_str, interval="1d", progress=False, auto_adjust=True)
    if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    if len(d) < 70: continue

    c = d["Close"].squeeze()
    o = d["Open"].squeeze()
    v = d["Volume"].squeeze()
    vol_mean = v.rolling(66).mean().shift(1)
    vol_std  = v.rolling(66).std().shift(1)
    abnvol   = (v - vol_mean) / vol_std
    dayret   = (c - o) / o

    # Yesterday's signal → enter today
    if abnvol.iloc[-2] > VOL_THRESHOLD and dayret.iloc[-2] > PRICE_THRESHOLD:
        price = float(c.iloc[-1])
        risk_amt = equity * RISK_PER_SYM * size_mult
        shares = int(risk_amt / (price * STOP_PCT))
        if shares < 1:
            print(f"  {sym}: signal but position too small — skip")
            continue
        signals.append({
            "symbol": sym,
            "shares": shares,
            "price":  price,
            "abnvol": float(abnvol.iloc[-2]),
            "dayret": float(dayret.iloc[-2]),
        })
        print(f"  🚨 {sym}: abnvol={abnvol.iloc[-2]:.2f}, dayret={dayret.iloc[-2]:+.2%} → BUY {shares} shares")
    else:
        print(f"  {sym}: no signal (abnvol={abnvol.iloc[-2]:.2f})")

# ── EXECUTE SIGNALS ──
if signals:
    print(f"\nExecuting {len(signals)} order(s)...")
    for sig in signals:
        try:
            order = trading.submit_order(MarketOrderRequest(
                symbol=sig["symbol"],
                qty=sig["shares"],
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            ))
            print(f"  ✅ {sig['symbol']}: BUY {sig['shares']} shares @ ~${sig['price']:.2f} | Order: {order.id}")
        except Exception as e:
            print(f"  ❌ {sig['symbol']}: order failed — {e}")
else:
    print("\nNo signals today — no orders placed.")

# ── DAILY SUMMARY ──
account = trading.get_account()
equity_now = float(account.equity)
print(f"\n{'='*55}")
print(f"End of day equity: ${equity_now:,.2f}")
print(f"Open positions:    {[p.symbol for p in trading.get_all_positions()]}")
print(f"Next run:          tomorrow after 4pm ET")
print(f"{'='*55}")
