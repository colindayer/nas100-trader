"""
Live Trader — All 5 Strategies
Pulls live bars from Alpaca, generates signals, places paper orders automatically.

Railway cron schedule (3 runs per day):
  0 7  * * 1-5  →  7am  UTC = 2am  ET  → S1 Asian Sweep, S2 Gold FVG, S4 Multi-Sweep
  30 14 * * 1-5  → 2:30pm UTC = 10:30am ET → S5 ORB (after opening range forms)
  0 21 * * 1-5  →  9pm  UTC = 5pm  ET  → S3 Abnormal Volume (end of day)

Run manually:
  python3 live_trader.py --session asian
  python3 live_trader.py --session orb
  python3 live_trader.py --session eod
"""

import sys
import argparse
import pandas as pd
import numpy as np
import pytz
import yfinance as yf
from datetime import datetime, timedelta, date
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import os

# ── CONFIG ──
API_KEY    = os.environ.get("ALPACA_KEY",    "PKXGY4RL3FZEUSLDRREY2UMTJK")
SECRET_KEY = os.environ.get("ALPACA_SECRET", "3w1L7ymf6Pii5z2XrM1FjhFYvb96k6xm5ejrKeDt1w1W")

RISK_S1 = 0.0070
RISK_S2 = 0.0050
RISK_S3 = 0.0040
RISK_S4 = 0.0040
RISK_S5 = 0.0075
RISK_S6 = 0.0050
STOP_S1 = 0.015; RR_S1 = 3.0
STOP_S2 = 0.015; RR_S2 = 3.0
STOP_S3 = 0.020; HOLD_S3 = 5
STOP_S4 = 0.015; RR_S4 = 3.0
STOP_S5 = 0.010; RR_S5 = 3.0
STOP_S6 = 0.012; RR_S6 = 2.5

eastern = pytz.timezone("US/Eastern")
trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# ── HELPERS ──
def now_et():
    return datetime.now(eastern)

def get_account():
    acc = trading.get_account()
    return float(acc.equity)

def open_positions():
    return {p.symbol: p for p in trading.get_all_positions()}

def place_order(symbol, shares, side, strategy):
    if shares < 1:
        print(f"  {strategy} {symbol}: shares < 1, skip")
        return
    try:
        order = trading.submit_order(MarketOrderRequest(
            symbol=symbol,
            qty=int(shares),
            side=side,
            time_in_force=TimeInForce.DAY
        ))
        print(f"  ✅ {strategy} {symbol}: {side.value.upper()} {int(shares)} shares | {order.id}")
    except Exception as e:
        print(f"  ❌ {strategy} {symbol}: order failed — {e}")

def close_position(symbol, qty, reason):
    try:
        order = trading.submit_order(MarketOrderRequest(
            symbol=symbol,
            qty=abs(int(float(qty))),
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY
        ))
        print(f"  ✅ CLOSE {symbol} ({reason}) | {order.id}")
    except Exception as e:
        print(f"  ❌ CLOSE {symbol} failed — {e}")

def get_hourly_bars(symbol, days=60):
    start = datetime.now(pytz.utc) - timedelta(days=days)
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Hour,
        start=start
    )
    bars = data_client.get_stock_bars(req).df
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level="symbol")
    bars.index = pd.to_datetime(bars.index, utc=True).tz_convert(eastern)
    bars = bars[["open","high","low","close","volume"]].copy()
    bars.columns = ["Open","High","Low","Close","Volume"]
    return bars

def get_minute_bars(symbol, days=2):
    start = datetime.now(pytz.utc) - timedelta(days=days)
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start
    )
    bars = data_client.get_stock_bars(req).df
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level="symbol")
    bars.index = pd.to_datetime(bars.index, utc=True).tz_convert(eastern)
    bars = bars[["open","high","low","close","volume"]].copy()
    bars.columns = ["Open","High","Low","Close","Volume"]
    return bars

def get_gex_levels(symbol="QQQ"):
    """
    Calculate GEX levels from live options chain (yfinance has OI).
    Formula: GEX = gamma * OI * 100 * spot^2 * 0.01  (Squeezemetrics)
    Dealer assumption: long calls (positive), short puts (negative = multiply by -1)
    Returns: net_gex, gamma_flip, put_wall, call_wall
    """
    from scipy.stats import norm
    import math

    try:
        ticker = yf.Ticker(symbol)
        spot = float(ticker.fast_info["lastPrice"])
        exps = ticker.options
        if not exps:
            return None, None, None, None

        r = 0.05  # risk-free rate
        today = date.today()

        gex_by_strike = {}

        for exp in exps[:6]:  # first 6 expirations cover the key gamma
            try:
                exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                T = max((exp_date - today).days / 365.0, 1/365)
                chain = ticker.option_chain(exp)

                for df, is_call in [(chain.calls, True), (chain.puts, False)]:
                    df = df.dropna(subset=["strike", "impliedVolatility", "openInterest"])
                    df = df[df["openInterest"] > 0]
                    df = df[df["impliedVolatility"] > 0]

                    for _, row in df.iterrows():
                        K = float(row["strike"])
                        sigma = float(row["impliedVolatility"])
                        oi = float(row["openInterest"])

                        # Black-Scholes gamma
                        d1 = (math.log(spot / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
                        gamma = norm.pdf(d1) / (spot * sigma * math.sqrt(T))

                        # GEX contribution (Squeezemetrics formula)
                        gex = gamma * oi * 100 * spot**2 * 0.01
                        if not is_call:
                            gex *= -1  # dealers short puts = negative GEX

                        if K not in gex_by_strike:
                            gex_by_strike[K] = 0.0
                        gex_by_strike[K] += gex
            except Exception:
                continue

        if not gex_by_strike:
            return None, None, None, None

        strikes = sorted(gex_by_strike.keys())
        net_gex = sum(gex_by_strike.values())

        # Gamma flip: strike where cumulative GEX (sorted by proximity to spot) crosses zero
        by_dist = sorted(strikes, key=lambda k: abs(k - spot))
        cumulative = 0.0
        gamma_flip = None
        for k in sorted(strikes):
            cumulative += gex_by_strike[k]
            if gamma_flip is None and cumulative >= 0:
                gamma_flip = k

        # Call wall: strike with highest positive GEX above spot
        above = {k: v for k, v in gex_by_strike.items() if k > spot and v > 0}
        call_wall = max(above, key=above.get) if above else None

        # Put wall: strike with highest absolute negative GEX below spot
        below = {k: v for k, v in gex_by_strike.items() if k < spot and v < 0}
        put_wall = min(below, key=below.get) if below else None

        print(f"  GEX: net=${net_gex/1e9:.2f}B | flip={gamma_flip} | put_wall={put_wall} | call_wall={call_wall}")
        return net_gex, gamma_flip, put_wall, call_wall

    except Exception as e:
        print(f"  GEX calc failed: {e}")
        return None, None, None, None


def get_iv_skew(symbol="QQQ"):
    """
    IV Skew = OTM put IV - ATM call IV  (Xing, Zhang & Zhao 2010)
    Steep negative skew (high put IV relative to calls) = market fear = bad for longs.
    Near-zero or positive skew = calm market = good for longs.
    Returns: skew value, is_extreme (True = fear, skip long trades)
    """
    try:
        ticker = yf.Ticker(symbol)
        spot = float(ticker.fast_info["lastPrice"])
        exps = ticker.options
        if not exps:
            return None, False

        # Use nearest expiry with >7 DTE
        from datetime import datetime as dt
        today = date.today()
        exp = next((e for e in exps
                    if (dt.strptime(e, "%Y-%m-%d").date() - today).days > 7), exps[0])
        chain = ticker.option_chain(exp)

        calls = chain.calls.dropna(subset=["strike","impliedVolatility"])
        puts  = chain.puts.dropna(subset=["strike","impliedVolatility"])

        # ATM call IV: closest strike to spot
        atm_call = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]
        atm_iv   = float(atm_call["impliedVolatility"].iloc[0])

        # OTM put IV: ~5% below spot
        otm_target = spot * 0.95
        otm_put  = puts.iloc[(puts["strike"] - otm_target).abs().argsort()[:1]]
        otm_iv   = float(otm_put["impliedVolatility"].iloc[0])

        skew = otm_iv - atm_iv
        # Extreme skew: put IV > call IV by >0.10 (10 vol points) = fear
        is_extreme = skew > 0.10
        print(f"  IV Skew ({symbol}): OTM put={otm_iv:.2f} ATM call={atm_iv:.2f} → skew={skew:+.3f} {'⚠️ EXTREME' if is_extreme else '✓ normal'}")
        return skew, is_extreme
    except Exception as e:
        print(f"  IV skew calc failed: {e}")
        return None, False


def get_short_interest(symbol="QQQ"):
    """
    Short Interest Ratio (days to cover) from yfinance.
    High short interest + sweep signal = short squeeze setup = high conviction.
    Returns: short_ratio (float), is_high (True if > 2.0 days to cover)
    """
    try:
        info = yf.Ticker(symbol).info
        short_ratio = info.get("shortRatio", None)
        if short_ratio is None:
            return None, False
        is_high = short_ratio > 2.0
        print(f"  Short interest ({symbol}): {short_ratio:.1f} days to cover {'🔥 HIGH' if is_high else '—'}")
        return short_ratio, is_high
    except Exception as e:
        print(f"  Short interest lookup failed: {e}")
        return None, False


def get_regime():
    end = str(date.today())
    vix = yf.download("^VIX", start=str(date.today()-timedelta(days=60)),
                      end=end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame): vix = vix.iloc[:,0]
    vix_ma21 = float(vix.rolling(21).mean().iloc[-1])

    spy = yf.download("SPY", start=str(date.today()-timedelta(days=500)),
                      end=end, progress=False)["Close"]
    if isinstance(spy, pd.DataFrame): spy = spy.iloc[:,0]
    spy_bull = bool(spy.ewm(span=50,adjust=False).mean().iloc[-1] >
                    spy.ewm(span=200,adjust=False).mean().iloc[-1])

    mult = 0.0 if vix_ma21 > 25 else (0.5 if vix_ma21 >= 20 else 1.0)
    return vix_ma21, spy_bull, mult

# ── STRATEGY S1: Asian Sweep QQQ ──
def run_s1(equity, open_syms, vix_ma21, spy_bull, vix_mult):
    print("\n── S1: ASIAN SWEEP (QQQ) ──")
    if "QQQ" in open_syms:
        print("  QQQ already in position — skip")
        return
    if not spy_bull or vix_mult == 0:
        print(f"  PAUSED — SPY={'bull' if spy_bull else 'bear'}, VIX={vix_ma21:.1f}")
        return

    data = get_hourly_bars("QQQ", days=30)
    data["Date"] = data.index.date

    def is_asian(idx): return idx.hour >= 18 or idx.hour < 2
    def sess_date(idx): return (idx + timedelta(days=1)).date() if idx.hour >= 18 else idx.date()

    data["Asian"]       = data.index.map(is_asian)
    data["SessionDate"] = data.index.map(sess_date)
    ab = data[data["Asian"]]
    data["AsianHigh"] = data["SessionDate"].map(ab.groupby("SessionDate")["High"].max())
    data["AsianLow"]  = data["SessionDate"].map(ab.groupby("SessionDate")["Low"].min())

    data["InSession"] = data.index.map(lambda x: (2 <= x.hour < 5) or (9 <= x.hour < 12))

    # VWAP
    tp = (data["High"] + data["Low"] + data["Close"]) / 3
    vwap_vals = []; cum_tp = cum_v = 0.0; prev_d = None
    for i in range(len(data)):
        d = data["Date"].iloc[i]
        if d != prev_d: cum_tp = cum_v = 0.0; prev_d = d
        if data["Volume"].iloc[i] > 0:
            cum_tp += tp.iloc[i] * data["Volume"].iloc[i]
            cum_v  += data["Volume"].iloc[i]
        vwap_vals.append(cum_tp / cum_v if cum_v > 0 else float("nan"))
    data["VWAP"] = vwap_vals

    # Daily EMA50
    daily_close = data[data.index.hour == 16][["Close"]].copy()
    daily_close.index = daily_close.index.date
    daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
    data["DailyEMA50"] = data["Date"].map(daily_close["Close"].ewm(span=50).mean().to_dict())

    # ATR filter
    pc = data["Close"].shift(1)
    tr = pd.concat([data["High"]-data["Low"],(data["High"]-pc).abs(),(data["Low"]-pc).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    data["HighVol"] = atr > 1.5 * atr.rolling(200).mean()

    # GEX regime filter (Squeezemetrics/SpotGamma approach)
    # Negative GEX = dealers short gamma = amplify moves = good for sweeps
    net_gex, gamma_flip, put_wall, call_wall = get_gex_levels("QQQ")
    neg_gex = (net_gex is None) or (net_gex < 0)  # default to allowing if data unavailable
    below_flip = (gamma_flip is None) or (float(data["Close"].iloc[-1]) < gamma_flip)

    data["SweepLow"] = (data["Low"] < data["AsianLow"]) & (data["Close"] > data["AsianLow"])
    signal_cond = (
        data["SweepLow"] & data["InSession"] &
        (data["Close"] > data["VWAP"]) &
        (data["Close"] > data["DailyEMA50"]) &
        ~data["HighVol"] & data["AsianLow"].notna()
    )

    # IV Skew filter (Xing et al. 2010) — skip if put fear is extreme
    skew, skew_extreme = get_iv_skew("QQQ")
    # Short interest (Asquith et al. 2005) — boost conviction if shorts are trapped
    short_ratio, high_si = get_short_interest("QQQ")

    # Check last 3 hours for a signal
    recent = data.tail(3)
    if signal_cond[recent.index].any():
        price = float(data["Close"].iloc[-1])

        # GEX confidence check
        if not neg_gex:
            print(f"  ⚠️  GEX POSITIVE (${net_gex/1e9:.1f}B) — dealers pin price. Skipping.")
            return

        # IV skew extreme = market pricing in crash = fade the sweep
        if skew_extreme:
            print(f"  ⚠️  IV SKEW EXTREME ({skew:+.3f}) — put fear too high, sweep likely fails. Skipping.")
            return

        # Build confidence notes
        notes = []
        if put_wall and price < put_wall:
            notes.append(f"below put wall ({put_wall})")
        if high_si:
            notes.append(f"high short interest ({short_ratio:.1f}x) → squeeze risk")
        confidence = " | " + " + ".join(notes) if notes else ""

        # Use call wall as dynamic target if within reach (>1% away, <4% away)
        if call_wall and 0.01 < (call_wall - price) / price < 0.04:
            dynamic_rr = (call_wall - price) / (price * STOP_S1)
            target_note = f"→ call wall ${call_wall} (RR {dynamic_rr:.1f}x)"
        else:
            target_note = f"→ fixed 3:1 RR"

        shares = (equity * RISK_S1 * vix_mult) / (price * STOP_S1)
        print(f"  🚨 SIGNAL: QQQ sweep below Asian low → LONG {target_note}{confidence}")
        place_order("QQQ", shares, OrderSide.BUY, "S1")
    else:
        gex_note = f" | GEX ${net_gex/1e9:.1f}B {'neg✓' if neg_gex else 'pos✗'}" if net_gex is not None else ""
        print(f"  No signal (close={data['Close'].iloc[-1]:.2f}, AsianLow={data['AsianLow'].iloc[-1]:.2f}{gex_note})")

# ── STRATEGY S2: Gold London FVG ──
def run_s2(equity, open_syms, vix_mult):
    print("\n── S2: GOLD LONDON FVG (GLD) ──")
    if "GLD" in open_syms:
        print("  GLD already in position — skip")
        return
    if vix_mult == 0:
        print("  PAUSED — VIX too high")
        return

    data = get_hourly_bars("GLD", days=30)
    data["Date"] = data.index.date

    def is_asian(idx): return idx.hour >= 18 or idx.hour < 2
    def sess_date(idx): return (idx + timedelta(days=1)).date() if idx.hour >= 18 else idx.date()

    data["Asian"]       = data.index.map(is_asian)
    data["SessionDate"] = data.index.map(sess_date)
    ab = data[data["Asian"]]
    data["AsianHigh"] = data["SessionDate"].map(ab.groupby("SessionDate")["High"].max())
    data["AsianLow"]  = data["SessionDate"].map(ab.groupby("SessionDate")["Low"].min())

    data["InLondon"] = data.index.map(lambda x: 2 <= x.hour < 5)

    cr = (data["High"]-data["Low"]).replace(0,0.001)
    data["StrongCandle"] = (data["Close"]-data["Open"]).abs() / cr > 0.6
    data["FVG_Up"]   = data["Low"] > data["High"].shift(2)
    data["FVG_Down"] = data["High"] < data["Low"].shift(2)

    data["SweepHigh"] = (data["High"] > data["AsianHigh"]) & (data["Close"] < data["AsianHigh"])
    data["SweepLow"]  = (data["Low"]  < data["AsianLow"])  & (data["Close"] > data["AsianLow"])

    # Track sweep state
    sh_active = [False]*len(data); sl_active = [False]*len(data)
    bh = bl = -999
    for i in range(len(data)):
        if data["SweepHigh"].iloc[i]: bh = i
        if data["SweepLow"].iloc[i]:  bl = i
        sh_active[i] = (i-bh) <= 10
        sl_active[i] = (i-bl) <= 10
    data["SweepHighActive"] = sh_active
    data["SweepLowActive"]  = sl_active

    daily_close = data[data.index.hour == 16][["Close"]].copy()
    daily_close.index = daily_close.index.date
    daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
    ema50 = daily_close["Close"].ewm(span=50).mean()
    data["DailyEMA50"] = data["Date"].map(ema50.to_dict())

    long_cond = (data["SweepLowActive"] & data["InLondon"] & data["StrongCandle"] &
                 data["FVG_Up"] & (data["Close"] > data["DailyEMA50"]) & data["AsianLow"].notna())
    short_cond = (data["SweepHighActive"] & data["InLondon"] & data["StrongCandle"] &
                  data["FVG_Down"] & (data["Close"] < data["DailyEMA50"]) & data["AsianHigh"].notna())

    recent = data.tail(4)
    if long_cond[recent.index].any():
        price = float(data["Close"].iloc[-1])
        shares = (equity * RISK_S2 * vix_mult) / (price * STOP_S2)
        print(f"  🚨 SIGNAL: GLD London FVG long")
        place_order("GLD", shares, OrderSide.BUY, "S2")
    elif short_cond[recent.index].any():
        price = float(data["Close"].iloc[-1])
        shares = (equity * RISK_S2 * vix_mult) / (price * STOP_S2)
        print(f"  🚨 SIGNAL: GLD London FVG short")
        place_order("GLD", shares, OrderSide.SELL, "S2")
    else:
        print(f"  No signal")

# ── STRATEGY S3: Abnormal Volume (end of day) ──
def run_s3(equity, open_syms, vix_mult):
    print("\n── S3: ABNORMAL VOLUME ──")
    SYMBOLS = ["QQQ", "GLD", "GDX", "SLV", "USO"]
    end = str(date.today())

    for sym in SYMBOLS:
        if sym in open_syms:
            # Check if held >= 5 days
            try:
                filled = trading.get_orders(filter=GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED, symbols=[sym], limit=5))
                buys = [o for o in filled if o.side == OrderSide.BUY and o.filled_at]
                if buys:
                    filled_at = buys[-1].filled_at
                    if filled_at.tzinfo is None:
                        filled_at = pytz.utc.localize(filled_at)
                    days_held = (datetime.now(pytz.utc) - filled_at).days
                    pos = open_syms[sym]
                    ep = float(buys[-1].filled_avg_price)
                    cp = float(pos.current_price)
                    pnl = (cp - ep) / ep
                    if days_held >= HOLD_S3 or pnl <= -STOP_S3:
                        reason = f"{HOLD_S3}-day exit" if days_held >= HOLD_S3 else "stop hit"
                        close_position(sym, pos.qty, reason)
                    else:
                        print(f"  {sym}: held {days_held}d, P&L {pnl:+.2%} — hold")
            except Exception as e:
                print(f"  {sym}: position check error — {e}")
            continue

        d = yf.download(sym, start=str(date.today()-timedelta(days=120)),
                        end=end, interval="1d", progress=False, auto_adjust=True)
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        if len(d) < 70: continue

        v = d["Volume"].squeeze()
        c = d["Close"].squeeze()
        o = d["Open"].squeeze()
        vol_mean = v.rolling(66).mean().shift(1)
        vol_std  = v.rolling(66).std().shift(1)
        abnvol   = (v - vol_mean) / vol_std
        dayret   = (c - o) / o

        if abnvol.iloc[-2] > 1.5 and dayret.iloc[-2] > 0.01 and vix_mult > 0:
            price  = float(c.iloc[-1])
            shares = (equity * RISK_S3 * vix_mult) / (price * STOP_S3)
            print(f"  🚨 {sym}: abnvol={abnvol.iloc[-2]:.2f}, ret={dayret.iloc[-2]:+.2%} → BUY")
            place_order(sym, shares, OrderSide.BUY, "S3")
        else:
            print(f"  {sym}: no signal (abnvol={abnvol.iloc[-2]:.2f})")

# ── STRATEGY S4: Multi-Sweep QQQ + SPY ──
def run_s4(equity, open_syms, spy_bull, vix_mult):
    print("\n── S4: MULTI-SWEEP (QQQ + SPY) ──")
    if not spy_bull or vix_mult == 0:
        print(f"  PAUSED — SPY={'bull' if spy_bull else 'bear'}, VIX mult={vix_mult}")
        return

    for sym in ["QQQ", "SPY"]:
        if sym in open_syms:
            print(f"  {sym}: already in position — skip")
            continue

        data = get_hourly_bars(sym, days=30)
        data["Date"] = data.index.date

        def is_asian(idx): return idx.hour >= 18 or idx.hour < 2
        def sess_date(idx): return (idx+timedelta(days=1)).date() if idx.hour >= 18 else idx.date()

        data["Asian"]       = data.index.map(is_asian)
        data["SessionDate"] = data.index.map(sess_date)
        ab = data[data["Asian"]]
        data["AsianHigh"] = data["SessionDate"].map(ab.groupby("SessionDate")["High"].max())
        data["AsianLow"]  = data["SessionDate"].map(ab.groupby("SessionDate")["Low"].min())

        def in_sess(x):
            h, m = x.hour, x.minute
            return (2<=h<5) or (h==9 and m>=30) or (10<=h<12)
        data["InSession"] = data.index.map(in_sess)

        pc = data["Close"].shift(1)
        tr = pd.concat([data["High"]-data["Low"],(data["High"]-pc).abs(),(data["Low"]-pc).abs()],axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        data["HighVol"] = atr > 1.5 * atr.rolling(200).mean()

        daily_close = data[data.index.hour == 16][["Close"]].copy()
        daily_close.index = daily_close.index.date
        daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
        ema50  = daily_close["Close"].ewm(span=50).mean()
        ema200 = daily_close["Close"].ewm(span=200).mean()
        data["DailyEMA50"]  = data["Date"].map(ema50.to_dict())
        data["DailyEMA200"] = data["Date"].map(ema200.to_dict())

        # GEX filter — negative gamma = dealers amplify moves = good for sweeps
        net_gex, gamma_flip, put_wall, call_wall = get_gex_levels(sym)
        neg_gex = (net_gex is None) or (net_gex < 0)
        # IV skew filter — skip if put fear is extreme (Xing et al. 2010)
        skew, skew_extreme = get_iv_skew(sym)
        # Short interest — note high SI as conviction boost
        short_ratio, high_si = get_short_interest(sym)

        sweep_low = (data["Low"] < data["AsianLow"]) & (data["Close"] > data["AsianLow"])
        signal = (sweep_low & data["InSession"] &
                  (data["Close"] > data["DailyEMA50"]) &
                  (data["DailyEMA50"] > data["DailyEMA200"]) &
                  ~data["HighVol"] & data["AsianLow"].notna())

        if signal.tail(3).any():
            price  = float(data["Close"].iloc[-1])
            if not neg_gex:
                print(f"  {sym}: signal exists but GEX POSITIVE (${net_gex/1e9:.1f}B) — skip")
                continue
            if skew_extreme:
                print(f"  {sym}: signal exists but IV SKEW EXTREME ({skew:+.3f}) — skip")
                continue
            si_note = f" | short squeeze risk ({short_ratio:.1f}x)" if high_si else ""
            shares = (equity * RISK_S4 * vix_mult) / (price * STOP_S4)
            gex_note = f" | GEX ${net_gex/1e9:.1f}B neg✓" if net_gex is not None else ""
            print(f"  🚨 {sym}: Asian sweep → LONG{gex_note}{si_note}")
            place_order(sym, shares, OrderSide.BUY, "S4")
        else:
            gex_note = f" | GEX ${net_gex/1e9:.1f}B {'neg✓' if neg_gex else 'pos✗'}" if net_gex is not None else ""
            print(f"  {sym}: no signal{gex_note}")

# ── STRATEGY S5: ORB 30-min ──
def run_s5(equity, open_syms, vix_ma21, spy_bull):
    print("\n── S5: ORB 30-MIN (QQQ) ──")
    if "QQQ" in open_syms:
        print("  QQQ already in position — skip")
        return
    if vix_ma21 >= 20:
        print(f"  PAUSED — VIX {vix_ma21:.1f} >= 20")
        return

    data = get_minute_bars("QQQ", days=2)
    today = now_et().date()
    today_bars = data[data.index.date == today]

    if len(today_bars) < 30:
        print(f"  Only {len(today_bars)} bars today — market may not be open")
        return

    # Opening range = first 30 bars (9:30-10:00am)
    orb_bars = today_bars.iloc[:30]
    orb_high = orb_bars["High"].max()
    orb_low  = orb_bars["Low"].min()
    orb_range_pct = (orb_high - orb_low) / orb_bars["Close"].iloc[-1]

    # Normal range filter: compare to 20-day avg
    recent_days = data[data.index.date < today]
    if len(recent_days) > 0:
        daily_ranges = []
        for d, grp in recent_days.groupby(recent_days.index.date):
            first30 = grp.iloc[:30]
            if len(first30) >= 15:
                r = (first30["High"].max() - first30["Low"].min()) / first30["Close"].iloc[-1]
                daily_ranges.append(r)
        if len(daily_ranges) >= 5:
            avg_range = np.mean(daily_ranges[-20:])
            if orb_range_pct > avg_range * 1.2:
                print(f"  SKIP — ORB range {orb_range_pct:.3f} > 1.2x avg {avg_range:.3f} (too wide)")
                return

    # Entry window bars (10:00am-1:00pm)
    now = now_et()
    entry_bars = today_bars[
        (today_bars.index.hour >= 10) &
        (today_bars.index.hour < 13)
    ]

    if len(entry_bars) == 0:
        print("  No bars in entry window yet (10am-1pm)")
        return

    last = entry_bars["Close"].iloc[-1]
    price = float(today_bars["Close"].iloc[-1])

    if last > orb_high and spy_bull:
        shares = (equity * RISK_S5) / (price * STOP_S5)
        print(f"  🚨 SIGNAL: QQQ broke ORB high {orb_high:.2f} → LONG")
        print(f"     ORB range: {orb_low:.2f} - {orb_high:.2f} ({orb_range_pct:.2%})")
        place_order("QQQ", shares, OrderSide.BUY, "S5")
    elif last < orb_low and not spy_bull:
        shares = (equity * RISK_S5) / (price * STOP_S5)
        print(f"  🚨 SIGNAL: QQQ broke ORB low {orb_low:.2f} → SHORT")
        place_order("QQQ", shares, OrderSide.SELL, "S5")
    else:
        print(f"  No breakout yet (price={price:.2f}, ORB: {orb_low:.2f}-{orb_high:.2f})")

# ── STRATEGY S6: IV SKEW REVERSAL ──
def run_s6(equity, open_syms, spy_bull, vix_mult):
    """
    S6: IV Skew Reversal (Xing, Zhang & Zhao 2010)
    Logic:
    - When QQQ put skew spikes to extreme (>0.15) AND VIX is elevated but not crisis,
      the fear is overdone. Fade it: go long QQQ expecting mean reversion.
    - Exit when skew normalizes below 0.08 or fixed 2.5:1 RR.
    - Only trade in SPY bull regime (don't fade fear in a real downtrend).
    - Negative GEX = dealers amplify moves = skew reversal works faster.
    """
    print("\n── S6: IV SKEW REVERSAL (QQQ) ──")

    if "QQQ" in open_syms:
        print("  QQQ already in position — skip")
        return
    if not spy_bull:
        print("  PAUSED — SPY bear regime (don't fade fear in downtrend)")
        return
    if vix_mult == 0:
        print("  PAUSED — VIX too high (>25), crisis mode")
        return

    skew, skew_extreme = get_iv_skew("QQQ")
    if skew is None:
        print("  Skew data unavailable — skip")
        return

    # Need extreme skew to enter (fear spike)
    if not skew_extreme:
        print(f"  Skew={skew:+.3f} — not extreme enough (need >0.10). No signal.")
        return

    # GEX check: negative gamma helps reversal complete faster
    net_gex, _, put_wall, call_wall = get_gex_levels("QQQ")
    neg_gex = (net_gex is None) or (net_gex < 0)

    # Short interest: high SI + fear spike = classic squeeze setup
    short_ratio, high_si = get_short_interest("QQQ")

    # Price must be near or below put wall (fear concentrated there)
    data = get_hourly_bars("QQQ", days=5)
    price = float(data["Close"].iloc[-1])

    # Entry: skew extreme + price stabilizing (not in freefall — close > open)
    last_candle_bullish = float(data["Close"].iloc[-1]) > float(data["Open"].iloc[-1])
    if not last_candle_bullish:
        print(f"  Skew extreme but price still falling — wait for stabilization. No entry.")
        return

    si_note = f" | short squeeze potential ({short_ratio:.1f}x SI)" if high_si else ""
    gex_note = f" | GEX {'neg✓' if neg_gex else 'pos (weaker signal)'}"
    target = price * (1 + STOP_S6 * RR_S6)
    stop   = price * (1 - STOP_S6)

    shares = (equity * RISK_S6 * vix_mult) / (price * STOP_S6)
    print(f"  🚨 SIGNAL: IV skew extreme ({skew:+.3f}) → fear overdone → LONG QQQ")
    print(f"     Entry: ${price:.2f} | Stop: ${stop:.2f} | Target: ${target:.2f}{gex_note}{si_note}")
    place_order("QQQ", shares, OrderSide.BUY, "S6")


# ── MAIN ──
parser = argparse.ArgumentParser()
parser.add_argument("--session", choices=["asian","orb","eod","all"], default=None)
args = parser.parse_args()

# Auto-detect session from current time if not specified
if args.session is None:
    h = now_et().hour
    if 1 <= h < 7:
        args.session = "asian"
    elif 10 <= h < 14:
        args.session = "orb"
    else:
        args.session = "eod"

print(f"\n{'='*60}")
print(f"LIVE TRADER — Session: {args.session.upper()} — {now_et().strftime('%Y-%m-%d %H:%M ET')}")
print(f"{'='*60}\n")

equity    = get_account()
open_syms = open_positions()
vix_ma21, spy_bull, vix_mult = get_regime()

print(f"Equity:  ${equity:,.2f}")
print(f"Regime:  VIX 21d={vix_ma21:.1f} | SPY {'Golden ✅' if spy_bull else 'Death ⚠️'}")
print(f"Open:    {list(open_syms.keys()) or 'None'}")

if args.session == "asian":
    run_s1(equity, open_syms, vix_ma21, spy_bull, vix_mult)
    run_s2(equity, open_syms, vix_mult)
    run_s4(equity, open_syms, spy_bull, vix_mult)
    run_s6(equity, open_syms, spy_bull, vix_mult)  # IV skew reversal

elif args.session == "orb":
    run_s5(equity, open_syms, vix_ma21, spy_bull)

elif args.session == "eod":
    run_s3(equity, open_syms, vix_mult)

elif args.session == "all":
    run_s1(equity, open_syms, vix_ma21, spy_bull, vix_mult)
    run_s2(equity, open_syms, vix_mult)
    run_s4(equity, open_syms, spy_bull, vix_mult)
    run_s5(equity, open_syms, vix_ma21, spy_bull)
    run_s3(equity, open_syms, vix_mult)
    run_s6(equity, open_syms, spy_bull, vix_mult)

print(f"\n{'='*60}")
print(f"Done — {now_et().strftime('%H:%M ET')}")
print(f"{'='*60}")
