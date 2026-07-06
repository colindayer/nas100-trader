"""
Live Trader - All 5 Strategies
Broker-agnostic: use --broker {alpaca,tradovate,ctrader} (default: alpaca)
Use --dry-run to print intended orders without placing them.

Railway cron schedule (3 runs per day):
  0 7  * * 1-5  ->  7am  UTC = 2am  ET  -> S1 Asian Sweep, S2 Gold FVG, S4 Multi-Sweep
  30 14 * * 1-5  -> 2:30pm UTC = 10:30am ET -> S5 ORB hourly (9:00 opening range done, breakout window 10-13)
  0 21 * * 1-5  ->  9pm  UTC = 5pm  ET  -> S3 Abnormal Volume (end of day)

Run manually:
  python3 live_trader.py --session asian
  python3 live_trader.py --broker ctrader --session orb --dry-run
  python3 live_trader.py --broker tradovate --session eod
"""

import sys
import argparse
import configparser
import logging
import os
from logging.handlers import RotatingFileHandler

import pandas as pd
import numpy as np
import pytz
import yfinance as yf
from datetime import datetime, timedelta, date
try:
    from alpaca.trading.enums import OrderSide  # only needed for the Alpaca S3 position-check
except ImportError:
    OrderSide = None  # not installed (e.g. MT5-only VPS) - the Alpaca-only path won't run

import alerts
from broker import load_config, DryRunBroker

# Force UTF-8 on stdout/stderr. Scheduled Windows tasks redirect output to a log
# file encoded cp1252, which cannot encode emoji ([OK] [OK]) - that raised
# UnicodeEncodeError and crashed EVERY scheduled run with exit code 1 *before any
# strategy was evaluated* (manual runs to a UTF-8 console were fine, masking it).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# -- LOGGING ------------------------------------------------------------------
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
            exist_ok=True)
_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "logs", "trader.log")
_handler = RotatingFileHandler(_log_path, maxBytes=5_000_000, backupCount=5)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger = logging.getLogger("trader")
logger.addHandler(_handler)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)

# -- RISK CONSTANTS (unchanged from validated backtest) ------------------------
RISK_S1 = 0.0070
RISK_S2 = 0.0050
RISK_S3 = 0.0040
RISK_S4 = 0.0040
RISK_S5 = 0.0075
STOP_S1 = 0.015; RR_S1 = 3.0
STOP_S2 = 0.015; RR_S2 = 3.0
STOP_S3 = 0.020; HOLD_S3 = 5
STOP_S4 = 0.015; RR_S4 = 3.0
STOP_S5 = 0.010; RR_S5 = 3.0
RISK_BTC = 0.006; STOP_BTC = 0.025; RR_BTC = 3.0   # BTC sweep (pillar #3, vol-scaled stop)

eastern = pytz.timezone("US/Eastern")

# Kill-switch: daily loss limit from [risk] section (default 5%)
_risk_cfg      = load_config("risk")
DAILY_KILL_PCT = float(_risk_cfg.get("daily_loss_limit", "0.05"))

# Conformal DD-throttle (Schmitt 2026): target drawdown cap. Position size scales
# down as live drawdown approaches this, holding the account well under prop limits.
# Validated: cut 3-pillar MaxDD -7.9%->-4.8%, Calmar 1.54->2.00. See FINDINGS.md.
TARGET_DD = float(_risk_cfg.get("target_drawdown", "0.08"))
MONTHLY_KILL_PCT = float(_risk_cfg.get("monthly_loss_limit", "0.04"))
_state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "logs", "risk_state.json")

def update_risk_state(equity, broker_name="default"):
    """Persist peak equity + month-start equity, PER BROKER (each account tracks
    its own - so Alpaca's $100k peak can't trigger a false drawdown on BTC's $25k).
    Returns: (dd_scale [0.3-1.0], cur_dd, peak, month_pnl_pct)."""
    import json
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "logs", f"risk_state_{broker_name}.json")
    st = {}
    try:
        with open(state_path) as f:
            st = json.load(f)
    except Exception:
        pass
    # peak equity (drawdown throttle)
    peak = max(float(st.get("peak_equity", equity)), equity)
    cur_dd = (equity - peak) / max(peak, 1)                      # <= 0
    scale = max(0.3, min(1.0, (TARGET_DD + cur_dd) / TARGET_DD))
    # month-start equity (worst-month guard) - reset on new calendar month
    mkey = now_et().strftime("%Y-%m")
    if st.get("month_key") != mkey:
        st["month_key"] = mkey
        st["month_start_equity"] = equity
    m_start = float(st.get("month_start_equity", equity))
    month_pnl_pct = (equity - m_start) / max(m_start, 1)
    st["peak_equity"] = peak
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w") as f:
            json.dump(st, f)
    except Exception:
        pass
    return scale, cur_dd, peak, month_pnl_pct

# -- BROKER FACTORY ------------------------------------------------------------
def make_broker(name: str):
    if name == "alpaca":
        from alpaca_broker import AlpacaBroker
        return AlpacaBroker()
    if name == "tradovate":
        from tradovate_broker import TradovateBroker
        return TradovateBroker()
    if name == "ctrader":
        from ctrader_broker import CTraderBroker
        return CTraderBroker()
    if name == "binance":
        from binance_broker import BinanceBroker
        return BinanceBroker()
    if name == "mt5":
        from mt5_broker import MT5Broker
        return MT5Broker()
    raise ValueError(f"Unknown broker: {name}")

# -- HELPERS -------------------------------------------------------------------
def now_et():
    return datetime.now(eastern)

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

    qqq = yf.download("QQQ", start=str(date.today()-timedelta(days=400)),
                      end=end, progress=False)["Close"]
    if isinstance(qqq, pd.DataFrame): qqq = qqq.iloc[:,0]
    qqq_bear200 = bool(float(qqq.iloc[-1]) < float(qqq.rolling(200).mean().iloc[-1]))

    mult = 0.0 if vix_ma21 > 25 else (0.5 if vix_ma21 >= 20 else 1.0)
    logger.info(f"REGIME vix_ma21={vix_ma21:.1f} spy_bull={spy_bull} "
                f"qqq_bear200={qqq_bear200} vix_mult={mult}")
    return vix_ma21, spy_bull, mult, qqq_bear200

def get_gex_levels(broker, symbol="QQQ"):
    from scipy.stats import norm
    import math
    try:
        ticker = yf.Ticker(symbol)
        spot = float(ticker.fast_info["lastPrice"])
        exps = ticker.options
        if not exps:
            return None, None, None, None
        r = 0.05; today = date.today(); gex_by_strike = {}
        for exp in exps[:6]:
            try:
                exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                T = max((exp_date - today).days / 365.0, 1/365)
                chain = ticker.option_chain(exp)
                for df, is_call in [(chain.calls, True), (chain.puts, False)]:
                    df = df.dropna(subset=["strike","impliedVolatility","openInterest"])
                    df = df[df["openInterest"] > 0]
                    df = df[df["impliedVolatility"] > 0]
                    for _, row in df.iterrows():
                        K = float(row["strike"]); sigma = float(row["impliedVolatility"])
                        oi = float(row["openInterest"])
                        d1 = (math.log(spot/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
                        gamma = norm.pdf(d1) / (spot*sigma*math.sqrt(T))
                        gex = gamma*oi*100*spot**2*0.01
                        if not is_call: gex *= -1
                        gex_by_strike[K] = gex_by_strike.get(K, 0.0) + gex
            except Exception:
                continue
        if not gex_by_strike:
            return None, None, None, None
        strikes = sorted(gex_by_strike.keys())
        net_gex = sum(gex_by_strike.values())
        cumulative = 0.0; gamma_flip = None
        for k in sorted(strikes):
            cumulative += gex_by_strike[k]
            if gamma_flip is None and cumulative >= 0: gamma_flip = k
        above = {k: v for k, v in gex_by_strike.items() if k > spot and v > 0}
        below = {k: v for k, v in gex_by_strike.items() if k < spot and v < 0}
        call_wall = max(above, key=above.get) if above else None
        put_wall  = min(below, key=below.get) if below else None
        logger.info(f"GEX {symbol}: net={net_gex/1e9:.2f}B flip={gamma_flip} "
                    f"put_wall={put_wall} call_wall={call_wall}")
        print(f"  GEX: net=${net_gex/1e9:.2f}B | flip={gamma_flip} | "
              f"put_wall={put_wall} | call_wall={call_wall}")
        return net_gex, gamma_flip, put_wall, call_wall
    except Exception as e:
        logger.warning(f"GEX calc failed for {symbol}: {e}")
        return None, None, None, None

# -- STRATEGY S1: Asian Sweep QQQ ---------------------------------------------
def run_s1(broker, equity, open_syms, vix_ma21, spy_bull, vix_mult):
    logger.info("SESSION S1 start")
    print("\n-- S1: ASIAN SWEEP (QQQ) --")
    if "QQQ" in open_syms:
        logger.info("S1 skip: QQQ already in position")
        print("  QQQ already in position - skip"); return
    # Bull filter REMOVED (validated: sweep works in bear too - OOS Sharpe 0.88->1.02,
    # +44%->+55%, same -10% DD). Keep only the extreme-VIX pause.
    if vix_mult == 0:
        logger.info("S1 pause: extreme VIX")
        print(f"  PAUSED - extreme VIX ({vix_ma21:.1f})"); return

    data = broker.get_bars("QQQ", "1Hour", 30)
    data["Date"] = data.index.date

    def is_asian(idx): return idx.hour >= 18 or idx.hour < 2
    def sess_date(idx): return (idx + timedelta(days=1)).date() if idx.hour >= 18 else idx.date()

    data["Asian"]       = data.index.map(is_asian)
    data["SessionDate"] = data.index.map(sess_date)
    ab = data[data["Asian"]]
    data["AsianHigh"] = data["SessionDate"].map(ab.groupby("SessionDate")["High"].max())
    data["AsianLow"]  = data["SessionDate"].map(ab.groupby("SessionDate")["Low"].min())
    data["InSession"] = data.index.map(lambda x: (2 <= x.hour < 5) or (9 <= x.hour < 12))

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

    daily_close = data[data.index.hour == 16][["Close"]].copy()
    daily_close.index = daily_close.index.date
    daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
    data["DailyEMA50"] = data["Date"].map(daily_close["Close"].ewm(span=50).mean().to_dict())

    pc = data["Close"].shift(1)
    tr = pd.concat([data["High"]-data["Low"],(data["High"]-pc).abs(),
                    (data["Low"]-pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    data["HighVol"] = atr > 1.5 * atr.rolling(200).mean()

    net_gex, gamma_flip, put_wall, call_wall = get_gex_levels(broker, "QQQ")
    neg_gex     = (net_gex is None) or (net_gex < 0)
    below_flip  = (gamma_flip is None) or (float(data["Close"].iloc[-1]) < gamma_flip)

    data["SweepLow"] = (data["Low"] < data["AsianLow"]) & (data["Close"] > data["AsianLow"])
    signal_cond = (data["SweepLow"] & data["InSession"] &
                   (data["Close"] > data["VWAP"]) &
                   (data["Close"] > data["DailyEMA50"]) &
                   ~data["HighVol"] & data["AsianLow"].notna())

    recent = data.tail(3)
    if signal_cond[recent.index].any():
        price = float(data["Close"].iloc[-1])
        if not neg_gex:
            logger.info(f"S1 skip: GEX positive ${net_gex/1e9:.1f}B")
            print(f"  GEX POSITIVE (${net_gex/1e9:.1f}B) - dealers pin price. Skipping."); return
        notes = []
        if put_wall and price < put_wall:
            notes.append(f"below put wall ({put_wall})")
        confidence = " | " + " + ".join(notes) if notes else ""
        if call_wall and 0.01 < (call_wall - price) / price < 0.04:
            target_note = f"-> call wall ${call_wall} (RR {(call_wall-price)/(price*STOP_S1):.1f}x)"
        else:
            target_note = "-> fixed 3:1 RR"
        shares = (equity * RISK_S1 * vix_mult * broker.RISK_SCALE) / (price * STOP_S1)
        logger.info(f"S1 SIGNAL QQQ sweep_low price={price:.2f} shares={shares:.1f}")
        print(f"  SIGNAL: QQQ sweep below Asian low {target_note}{confidence}")
        broker.place_order_safe("QQQ", shares, "buy", "S1")
    else:
        al = data["AsianLow"].iloc[-1]
        logger.info(f"S1 no signal: close={data['Close'].iloc[-1]:.2f} asian_low={al:.2f}")
        gex_note = (f" | GEX ${net_gex/1e9:.1f}B {'negok' if neg_gex else 'posx'}"
                    if net_gex is not None else "")
        print(f"  No signal (close={data['Close'].iloc[-1]:.2f}, AsianLow={al:.2f}{gex_note})")

# -- STRATEGY S2: Gold London FVG ---------------------------------------------
def run_s2(broker, equity, open_syms, vix_mult):
    logger.info("SESSION S2 start")
    print("\n-- S2: GOLD LONDON FVG (GLD) --")
    if "GLD" in open_syms:
        logger.info("S2 skip: GLD in position")
        print("  GLD already in position - skip"); return
    if vix_mult == 0:
        logger.info("S2 pause: VIX too high")
        print("  PAUSED - VIX too high"); return

    data = broker.get_bars("GLD", "1Hour", 30)
    data["Date"] = data.index.date

    def is_asian(idx): return idx.hour >= 18 or idx.hour < 2
    def sess_date(idx): return (idx + timedelta(days=1)).date() if idx.hour >= 18 else idx.date()

    data["Asian"]       = data.index.map(is_asian)
    data["SessionDate"] = data.index.map(sess_date)
    ab = data[data["Asian"]]
    data["AsianHigh"] = data["SessionDate"].map(ab.groupby("SessionDate")["High"].max())
    data["AsianLow"]  = data["SessionDate"].map(ab.groupby("SessionDate")["Low"].min())
    data["InLondon"]  = data.index.map(lambda x: 2 <= x.hour < 5)

    cr = (data["High"]-data["Low"]).replace(0, 0.001)
    data["StrongCandle"] = (data["Close"]-data["Open"]).abs() / cr > 0.6
    data["FVG_Up"]   = data["Low"]  > data["High"].shift(2)
    data["FVG_Down"] = data["High"] < data["Low"].shift(2)
    data["SweepHigh"] = (data["High"] > data["AsianHigh"]) & (data["Close"] < data["AsianHigh"])
    data["SweepLow"]  = (data["Low"]  < data["AsianLow"])  & (data["Close"] > data["AsianLow"])

    sh_active = [False]*len(data); sl_active = [False]*len(data); bh = bl = -999
    for i in range(len(data)):
        if data["SweepHigh"].iloc[i]: bh = i
        if data["SweepLow"].iloc[i]:  bl = i
        sh_active[i] = (i-bh) <= 10; sl_active[i] = (i-bl) <= 10
    data["SweepHighActive"] = sh_active; data["SweepLowActive"] = sl_active

    daily_close = data[data.index.hour == 16][["Close"]].copy()
    daily_close.index = daily_close.index.date
    daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
    data["DailyEMA50"] = data["Date"].map(
        daily_close["Close"].ewm(span=50).mean().to_dict())

    long_cond  = (data["SweepLowActive"]  & data["InLondon"] & data["StrongCandle"] &
                  data["FVG_Up"]   & (data["Close"] > data["DailyEMA50"]) & data["AsianLow"].notna())
    short_cond = (data["SweepHighActive"] & data["InLondon"] & data["StrongCandle"] &
                  data["FVG_Down"] & (data["Close"] < data["DailyEMA50"]) & data["AsianHigh"].notna())

    recent = data.tail(4)
    price  = float(data["Close"].iloc[-1])
    shares = (equity * RISK_S2 * vix_mult * broker.RISK_SCALE) / (price * STOP_S2)
    if long_cond[recent.index].any():
        logger.info(f"S2 SIGNAL GLD long price={price:.2f} shares={shares:.1f}")
        print("  SIGNAL: GLD London FVG long")
        broker.place_order_safe("GLD", shares, "buy", "S2")
    elif short_cond[recent.index].any():
        logger.info(f"S2 SIGNAL GLD short price={price:.2f} shares={shares:.1f}")
        print("  SIGNAL: GLD London FVG short")
        broker.place_order_safe("GLD", shares, "sell", "S2")
    else:
        logger.info("S2 no signal")
        print("  No signal")

# -- STRATEGY S3: Abnormal Volume (end of day) ---------------------------------
def run_s3(broker, equity, open_syms, vix_mult):
    logger.info("SESSION S3 start")
    print("\n-- S3: ABNORMAL VOLUME --")
    SYMBOLS = ["QQQ", "GLD", "GDX", "SLV", "USO"]
    end = str(date.today())

    for sym in SYMBOLS:
        if sym in open_syms:
            try:
                from alpaca.trading.requests import GetOrdersRequest
                from alpaca.trading.enums import QueryOrderStatus
                # Position exit logic only works with Alpaca (order history API)
                # For other brokers, log a reminder and skip the check
                if hasattr(broker, "_trade"):
                    filled = broker._trade.get_orders(filter=GetOrdersRequest(
                        status=QueryOrderStatus.CLOSED, symbols=[sym], limit=5))
                    buys = [o for o in filled
                            if o.side == OrderSide.BUY and o.filled_at]
                    if buys:
                        filled_at = buys[-1].filled_at
                        if filled_at.tzinfo is None:
                            import pytz as _tz; filled_at = _tz.utc.localize(filled_at)
                        days_held = (datetime.now(pytz.utc) - filled_at).days
                        pos = open_syms[sym]
                        ep = float(buys[-1].filled_avg_price)
                        cp = float(pos.current_price)
                        pnl = (cp - ep) / ep
                        if days_held >= HOLD_S3 or pnl <= -STOP_S3:
                            reason = f"{HOLD_S3}-day exit" if days_held >= HOLD_S3 else "stop hit"
                            logger.info(f"S3 EXIT {sym} reason={reason} pnl={pnl:.2%}")
                            broker.close_position(sym)
                        else:
                            logger.info(f"S3 hold {sym} days={days_held} pnl={pnl:.2%}")
                            print(f"  {sym}: held {days_held}d, P&L {pnl:+.2%} - hold")
                else:
                    logger.info(f"S3 {sym}: in position; manual exit check needed for non-Alpaca broker")
                    print(f"  {sym}: in position (manual exit check for {type(broker).__name__})")
            except Exception as e:
                logger.error(f"S3 position check error {sym}: {e}")
                print(f"  {sym}: position check error - {e}")
            continue

        d = yf.download(sym, start=str(date.today()-timedelta(days=120)),
                        end=end, interval="1d", progress=False, auto_adjust=True)
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        if len(d) < 70: continue

        v = d["Volume"].squeeze(); c = d["Close"].squeeze(); o = d["Open"].squeeze()
        vol_mean = v.rolling(66).mean().shift(1); vol_std = v.rolling(66).std().shift(1)
        abnvol = (v - vol_mean) / vol_std; dayret = (c - o) / o

        if abnvol.iloc[-2] > 1.5 and dayret.iloc[-2] > 0.01 and vix_mult > 0:
            price  = float(c.iloc[-1])
            shares = (equity * RISK_S3 * vix_mult * broker.RISK_SCALE) / (price * STOP_S3)
            logger.info(f"S3 SIGNAL {sym} abnvol={abnvol.iloc[-2]:.2f} "
                        f"dayret={dayret.iloc[-2]:.2%} shares={shares:.1f}")
            print(f"  SIGNAL {sym}: abnvol={abnvol.iloc[-2]:.2f}, "
                  f"ret={dayret.iloc[-2]:+.2%} -> BUY")
            broker.place_order_safe(sym, shares, "buy", "S3")
        else:
            logger.info(f"S3 {sym}: no signal abnvol={abnvol.iloc[-2]:.2f}")
            print(f"  {sym}: no signal (abnvol={abnvol.iloc[-2]:.2f})")

# -- STRATEGY S4: Multi-Sweep QQQ + SPY ---------------------------------------
def run_s4(broker, equity, open_syms, spy_bull, vix_mult):
    logger.info("SESSION S4 start")
    print("\n-- S4: MULTI-SWEEP (QQQ + SPY) --")
    if not spy_bull or vix_mult == 0:
        logger.info(f"S4 pause: spy_bull={spy_bull} vix_mult={vix_mult}")
        print(f"  PAUSED - SPY={'bull' if spy_bull else 'bear'}, VIX mult={vix_mult}"); return

    for sym in ["QQQ", "SPY"]:
        if sym in open_syms:
            logger.info(f"S4 skip {sym}: in position")
            print(f"  {sym}: already in position - skip"); continue

        data = broker.get_bars(sym, "1Hour", 30)
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
        tr = pd.concat([data["High"]-data["Low"],(data["High"]-pc).abs(),
                        (data["Low"]-pc).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        data["HighVol"] = atr > 1.5 * atr.rolling(200).mean()

        daily_close = data[data.index.hour == 16][["Close"]].copy()
        daily_close.index = daily_close.index.date
        daily_close = daily_close[~daily_close.index.duplicated(keep="last")]
        ema50  = daily_close["Close"].ewm(span=50).mean()
        ema200 = daily_close["Close"].ewm(span=200).mean()
        data["DailyEMA50"]  = data["Date"].map(ema50.to_dict())
        data["DailyEMA200"] = data["Date"].map(ema200.to_dict())

        net_gex, _, _, _ = get_gex_levels(broker, sym)
        neg_gex = (net_gex is None) or (net_gex < 0)

        sweep_low = ((data["Low"] < data["AsianLow"]) & (data["Close"] > data["AsianLow"]))
        signal = (sweep_low & data["InSession"] &
                  (data["Close"] > data["DailyEMA50"]) &
                  (data["DailyEMA50"] > data["DailyEMA200"]) &
                  ~data["HighVol"] & data["AsianLow"].notna())

        if signal.tail(3).any():
            price = float(data["Close"].iloc[-1])
            if not neg_gex:
                logger.info(f"S4 skip {sym}: GEX positive ${net_gex/1e9:.1f}B")
                print(f"  {sym}: GEX POSITIVE (${net_gex/1e9:.1f}B) - skip"); continue
            shares = (equity * RISK_S4 * vix_mult * broker.RISK_SCALE) / (price * STOP_S4)
            gex_note = f" | GEX ${net_gex/1e9:.1f}B negok" if net_gex is not None else ""
            logger.info(f"S4 SIGNAL {sym} price={price:.2f} shares={shares:.1f}")
            print(f"  SIGNAL {sym}: Asian sweep -> LONG{gex_note}")
            broker.place_order_safe(sym, shares, "buy", "S4")
        else:
            gex_note = (f" | GEX ${net_gex/1e9:.1f}B {'negok' if neg_gex else 'posx'}"
                        if net_gex is not None else "")
            logger.info(f"S4 {sym}: no signal")
            print(f"  {sym}: no signal{gex_note}")

# -- STRATEGY S5: ORB (validated HOURLY version) -------------------------------
# Opening range = the 9:00 ET hourly bar; breakout window 10:00-13:00 ET; volume
# confirmation (>0.6x opening-range volume). Long needs SPY-bull regime; short
# needs Faber bear (QQQ < 200d SMA). This matches the walk-forward-validated edge
# (7/7 windows, Sharpe 3.21). The old 30-min/1-min version was the losing one.
def run_s5(broker, equity, open_syms, vix_ma21, spy_bull, qqq_bear200):
    logger.info("SESSION S5 start")
    print("\n-- S5: ORB HOURLY (QQQ) --")
    if "QQQ" in open_syms:
        logger.info("S5 skip: QQQ in position")
        print("  QQQ already in position - skip"); return
    if vix_ma21 >= 20:
        logger.info(f"S5 pause: VIX {vix_ma21:.1f} >= 20")
        print(f"  PAUSED - VIX {vix_ma21:.1f} >= 20"); return

    data = broker.get_bars("QQQ", "1Hour", 5)
    today = now_et().date()
    today_bars = data[data.index.date == today]

    # Opening range = the 9:00 ET hourly bar (matches the backtest's hour==9 bar)
    or_bar = today_bars[today_bars.index.hour == 9]
    if len(or_bar) == 0:
        logger.info("S5: opening-range (9:00 ET) bar not formed yet")
        print("  Opening-range bar (9:00 ET) not formed yet - wait"); return
    orb_high = float(or_bar["High"].iloc[0])
    orb_low  = float(or_bar["Low"].iloc[0])
    orb_vol  = float(or_bar["Volume"].iloc[0])

    # Breakout window = hours 10-13 ET
    cur = today_bars[(today_bars.index.hour >= 10) & (today_bars.index.hour <= 13)]
    if len(cur) == 0:
        logger.info("S5: no bars in breakout window yet (10-13 ET)")
        print("  No bars in breakout window yet (10:00-13:00 ET)"); return

    price   = float(cur["Close"].iloc[-1])
    cur_vol = float(cur["Volume"].iloc[-1])
    vol_ok  = cur_vol > orb_vol * 0.6          # volume confirmation (validated)
    print(f"  ORB(9:00): {orb_low:.2f}-{orb_high:.2f} | price {price:.2f} | vol_ok={vol_ok}")

    if price > orb_high and spy_bull and vol_ok:
        shares = (equity * RISK_S5 * broker.RISK_SCALE) / (price * STOP_S5)
        logger.info(f"S5 SIGNAL QQQ ORB long price={price:.2f} shares={shares:.1f}")
        print(f"  SIGNAL: QQQ broke ORB high {orb_high:.2f} -> LONG")
        broker.place_order_safe("QQQ", shares, "buy", "S5")
    elif price < orb_low and qqq_bear200 and vol_ok:
        shares = (equity * RISK_S5 * broker.RISK_SCALE) / (price * STOP_S5)
        logger.info(f"S5 SIGNAL QQQ ORB short price={price:.2f} shares={shares:.1f}")
        print(f"  SIGNAL: QQQ broke ORB low {orb_low:.2f} -> SHORT (200d-SMA bear regime)")
        broker.place_order_safe("QQQ", shares, "sell", "S5")
    elif price < orb_low and not qqq_bear200:
        logger.info("S5: ORB-low break but bull regime - short disarmed")
        print("  ORB-low break but QQQ above 200d SMA - short disarmed (bull)")
    else:
        logger.info(f"S5: no breakout price={price:.2f} orb={orb_low:.2f}-{orb_high:.2f} vol_ok={vol_ok}")
        print(f"  No valid breakout (price={price:.2f}, ORB {orb_low:.2f}-{orb_high:.2f})")

# -- STRATEGY BTC: crypto Asian sweep (pillar #3, via Binance) -----------------
# Validated: 10/12 walk-forward windows, uncorrelated to Nasdaq (+0.02). Asian range
# 00-08 UTC, reclaim window 08-16 UTC, EMA50>EMA200 uptrend. 2.5% stop, 3:1 RR.
# Crypto is 24/7 so the position is HELD to stop/target across runs (state-machine
# in logs/btc_state.json), not closed EOD. Run this hourly during 08-16 UTC.
_btc_state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "logs", "btc_state.json")

def run_btc(broker, equity, open_syms):
    import json
    logger.info("SESSION BTC start")
    print("\n-- BTC: ASIAN SWEEP (crypto) --")
    data = broker.get_bars("BTC", "1Hour", 400)
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    data.index = data.index.tz_convert("UTC")
    data["Date"] = data.index.date; data["H"] = data.index.hour
    price = float(data["Close"].iloc[-1])

    # -- manage open position (held to stop/target across runs) --
    st = {}
    try:
        with open(_btc_state_path) as f: st = json.load(f)
    except Exception:
        pass
    in_pos = st.get("active", False) or ("BTC" in open_syms)
    if st.get("active", False):
        if price <= st.get("stop", 0):
            logger.info(f"BTC exit STOP price={price:.0f}"); print(f"  EXIT stop @ {price:.0f}")
            broker.place_order_safe("BTC", st.get("qty", 0), "sell", "BTC"); st = {"active": False}
        elif price >= st.get("target", 1e12):
            logger.info(f"BTC exit TARGET price={price:.0f}"); print(f"  EXIT target @ {price:.0f}")
            broker.place_order_safe("BTC", st.get("qty", 0), "sell", "BTC"); st = {"active": False}
        else:
            print(f"  Holding BTC: price {price:.0f} | stop {st.get('stop',0):.0f} | target {st.get('target',0):.0f}")
        with open(_btc_state_path, "w") as f: json.dump(st, f)
        return
    if in_pos:
        print("  BTC position open (untracked) - skip new entry"); return

    # -- entry: sweep below Asian low + reclaim, in 08-16 UTC window, uptrend --
    # Trend from DAILY bars (the 400 hourly bars ~16d can't form a 200-day EMA).
    daily = broker.get_bars("BTC", "1Day", 250)
    dc = daily["Close"]
    ema50 = dc.ewm(span=50).mean(); ema200 = dc.ewm(span=200).mean()
    uptrend = bool(ema50.iloc[-1] > ema200.iloc[-1])
    today = data["Date"].iloc[-1]
    asian = data[(data["Date"] == today) & (data["H"] >= 0) & (data["H"] < 8)]
    if len(asian) == 0:
        print("  Asian range (00-08 UTC) not formed yet"); return
    asian_low = float(asian["Low"].min())
    h = data["H"].iloc[-1]
    in_window = 8 <= h < 16
    swept = (float(data["Low"].iloc[-1]) < asian_low) and (price > asian_low)
    # also accept sweep in last 3 bars then reclaim
    recent = data.tail(3)
    swept_recent = ((recent["Low"] < asian_low).any()) and (price > asian_low)

    if in_window and uptrend and (swept or swept_recent):
        stop = price * (1 - STOP_BTC); target = price * (1 + STOP_BTC * RR_BTC)
        qty = (equity * RISK_BTC * broker.RISK_SCALE) / (price * STOP_BTC)
        logger.info(f"BTC SIGNAL sweep+reclaim price={price:.0f} qty={qty:.5f}")
        print(f"  SIGNAL: BTC swept Asian low {asian_low:.0f} & reclaimed -> LONG")
        print(f"     entry {price:.0f} | stop {stop:.0f} | target {target:.0f}")
        oid = broker.place_order_safe("BTC", round(qty, 5), "buy", "BTC")
        if oid is not None:
            with open(_btc_state_path, "w") as f:
                json.dump({"active": True, "entry": price, "stop": stop,
                           "target": target, "qty": round(qty, 5)}, f)
    else:
        reason = ("not in 08-16 UTC window" if not in_window else
                  "not uptrend" if not uptrend else "no sweep+reclaim")
        logger.info(f"BTC no signal: {reason} (price={price:.0f} asian_low={asian_low:.0f})")
        print(f"  No signal ({reason}) | price {price:.0f} asian_low {asian_low:.0f} uptrend={uptrend}")


# -- PILLAR: monthly cross-sectional (cross-asset) momentum ---------------------
# Validated (2010-21 IS / 2022-26 OOS, costs on): OOS Sharpe 1.07, CAGR +15.6%,
# maxDD -16.7%, beats SPY risk-adjusted, survives the 2022 bear (rotates to
# bonds/gold/commodities). LOW frequency (~12 trades/yr) - this is a DIVERSIFIER,
# not a frequency booster. Holds positions for a month (unlike flat-by-EOD
# intraday), so it MUST run on its OWN account or it will clobber the intraday
# QQQ/SPY/GLD positions. Run monthly (e.g. 1st trading day) via --session rebal.
XSMOM_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "DBC"]
XSMOM_ALLOC = 0.20    # fraction of (dedicated) account equity this sleeve uses
XSMOM_TOPN  = 3       # hold the top-N by 12-1 month momentum, equal weight

def run_xsmom(broker, equity, open_syms):
    logger.info("SESSION XSMOM start")
    print("\n-- MONTHLY CROSS-ASSET MOMENTUM (rebalance) --")
    scores = {}
    for sym in XSMOM_UNIVERSE:
        try:
            d = broker.get_bars(sym, "1Day", 400)["Close"].dropna()
        except Exception as e:
            logger.warning(f"xsmom {sym} bars failed: {e}"); continue
        if len(d) < 260:
            logger.warning(f"xsmom {sym}: only {len(d)} daily bars, skip"); continue
        scores[sym] = float(d.iloc[-21] / d.iloc[-252] - 1)   # 12-1 month return
    if len(scores) < 4:
        logger.info("xsmom: insufficient data, no rebalance"); print("  insufficient data"); return
    ranked = sorted(scores, key=scores.get, reverse=True)
    target = ranked[:XSMOM_TOPN]
    print("  12-1 momentum: " + ", ".join(f"{s} {scores[s]:+.0%}" for s in ranked))
    print(f"  Target hold (top {XSMOM_TOPN}): {target}")
    logger.info(f"xsmom target={target} scores={ {k: round(v,3) for k,v in scores.items()} }")
    per = equity * XSMOM_ALLOC / XSMOM_TOPN
    # exit any universe names that dropped out of the target
    for sym in XSMOM_UNIVERSE:
        if sym in open_syms and sym not in target:
            print(f"  EXIT {sym} (fell out of top {XSMOM_TOPN})")
            broker.close_position(sym)
    # enter / adjust target names to equal weight
    for sym in target:
        try:
            price = float(broker.get_bars(sym, "1Day", 5)["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"xsmom {sym} price failed: {e}"); continue
        want = int(per / price)
        have = int(float(open_syms[sym].qty)) if sym in open_syms else 0
        delta = want - have
        if delta > 0:
            broker.place_order_safe(sym, delta, "buy", "XSMOM")
        elif delta < 0:
            broker.place_order_safe(sym, -delta, "sell", "XSMOM")
        else:
            print(f"  {sym}: already at target ({have} sh)")


# -- PILLAR: midweek overnight drift (validated edge) ---------------------------
# Long QQQ overnight ONLY into Tue & Wed mornings (hold close->open), flat otherwise.
# Validated: 15-ticker cross-section, OOS Sharpe 0.68, maxDD -14%, ~103 trades/yr,
# Tue overnight positive in 100% of tickers OOS. Mon/Thu/Fri overnight are negative.
# Enter at/near close (>=15:30 ET) on Mon/Tue; exit at/near open (<11:00 ET) Tue/Wed.
_ovn_state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "logs", "ovn_state.json")
OVN_SYMBOL = "QQQ"
OVN_ALLOC  = 0.25   # fraction of equity per overnight hold (low-DD edge can size up)

def run_overnight(broker, equity, open_syms):
    import json
    logger.info("SESSION OVERNIGHT start")
    print("\n-- MIDWEEK OVERNIGHT (QQQ, Tue+Wed nights) --")
    now = now_et(); wd = now.weekday(); hr = now.hour; mn = now.minute
    st = {}
    try:
        with open(_ovn_state_path) as f: st = json.load(f)
    except Exception:
        pass
    # Source of truth = the ACTUAL position (cloud runs are ephemeral; state file
    # doesn't persist on GitHub Actions, so checking open_syms prevents re-buying).
    held = (OVN_SYMBOL in open_syms) or st.get("active", False)
    in_open_window  = (hr == 9 and mn >= 30) or (hr == 10)   # ~09:30-11:00 ET
    in_close_window = (15 <= hr < 16)                        # 15:00-16:00 ET (wide for 30-min scheduler)

    # EXIT at the open on Tue(1)/Wed(2) if we're holding
    if held and in_open_window:
        print(f"  EXIT overnight {OVN_SYMBOL} at open")
        broker.close_position(OVN_SYMBOL)
        with open(_ovn_state_path, "w") as f: json.dump({"active": False}, f)
        return
    # ENTER at the close on Mon(0)/Tue(1) - overnight lands on Tue/Wed (the strong nights)
    if not held and in_close_window and wd in (0, 1):
        price = float(broker.get_bars(OVN_SYMBOL, "1Hour", 5)["Close"].iloc[-1])
        # fractional units: Alpaca floors to whole shares internally; MT5 converts to lots
        qty = round((equity * OVN_ALLOC) / price, 2)
        if qty > 0:
            print(f"  ENTER overnight {OVN_SYMBOL}: BUY {qty} @ ~{price:.2f} (into "
                  f"{'Tue' if wd==0 else 'Wed'} morning)")
            oid = broker.place_order_safe(OVN_SYMBOL, qty, "buy", "OVN")
            if oid is not None:
                with open(_ovn_state_path, "w") as f:
                    json.dump({"active": True, "qty": qty, "entry": price}, f)
        else:
            print("  qty too small, skip")
    else:
        reason = ("holding, waiting for open" if held else
                  "not Mon/Tue close window" if not in_close_window else "wrong weekday")
        logger.info(f"OVN no action: {reason} (wd={wd} {hr:02d}:{mn:02d} ET)")
        print(f"  No action ({reason})")


# -- PILLAR: vol-targeted BTC trend (validated reject, rescued by refining) -----
# Donchian 20/10 long/flat trend on BTC, sized by inverse-vol to a 20% target.
# Validated 2017-26: OOS Sharpe 0.67, maxDD -24% (raw was -44%), 33 OOS trades,
# corr to QQQ +0.12 (uncorrelated). Run daily. Rebalances to target each run.
BTC_TREND_VOLTARGET = 0.20
_btctrend_state = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "logs", "btc_trend_state.json")

def run_btc_trend(broker, equity, open_syms):
    import json
    logger.info("SESSION BTC-TREND start")
    print("\n-- BTC TREND (vol-targeted Donchian 20/10) --")
    daily = broker.get_bars("BTC", "1Day", 250)
    close = daily["Close"]
    if len(close) < 30:
        print("  not enough data"); return
    H = close.rolling(20).max().shift(1); L = close.rolling(10).min().shift(1)
    p = 0
    for i in range(len(close)):
        c = float(close.iloc[i])
        if p == 0 and c > (H.iloc[i] if pd.notna(H.iloc[i]) else 1e18): p = 1
        elif p == 1 and c < (L.iloc[i] if pd.notna(L.iloc[i]) else 0): p = 0
    in_trend = (p == 1)
    rvol = float(close.pct_change().rolling(20).std().iloc[-1]) * (365 ** 0.5)
    target_frac = min(BTC_TREND_VOLTARGET / rvol, 1.0) if (in_trend and rvol > 0) else 0.0
    price = float(close.iloc[-1])
    target_qty = round((equity * target_frac * broker.RISK_SCALE) / price, 5)
    # current qty held (state file; on the same account BTC may also be held by the sweep)
    st = {}
    try:
        with open(_btctrend_state) as f: st = json.load(f)
    except Exception: pass
    cur = float(st.get("qty", 0.0))
    delta = round(target_qty - cur, 5)
    print(f"  trend={'UP' if in_trend else 'flat'} vol={rvol:.0%} target_frac={target_frac:.2f} "
          f"target={target_qty} cur={cur} delta={delta}")
    if abs(delta) * price < max(10, equity * 0.01):
        print("  within tolerance, no rebalance")
        return
    side = "buy" if delta > 0 else "sell"
    broker.place_order_safe("BTC", abs(delta), side, "BTCTREND")
    with open(_btctrend_state, "w") as f:
        json.dump({"qty": target_qty, "price": price}, f)


# -- PILLAR: S1 sweep on a WIDER validated universe -----------------------------
# The Asian-sweep edge validated across SPY/IWM/GLD/AAPL/MSFT/NVDA (all OOS-positive,
# PF 1.1-1.9). Runs the same pre-GEX sweep on the basket -> 5-7x the trade count from
# the SAME validated edge. (QQQ stays in S1 with its GEX filter, to avoid doubling.)
SWEEP_BASKET = ["SPY", "IWM", "GLD", "XLK", "XLE", "AAPL", "MSFT", "NVDA", "AMZN"]

def _asian_sweep_fires(data):
    """(fires, price) for the Asian-low-sweep + VWAP reclaim + EMA + calm-vol signal."""
    data = data.copy(); data["Date"] = data.index.date
    def is_asian(i): return i.hour >= 18 or i.hour < 2
    def sess_date(i): return (i + timedelta(days=1)).date() if i.hour >= 18 else i.date()
    data["Asian"] = data.index.map(is_asian); data["SD"] = data.index.map(sess_date)
    ab = data[data["Asian"]]
    data["AsianLow"] = data["SD"].map(ab.groupby("SD")["Low"].min())
    data["InSession"] = data.index.map(lambda x: (2 <= x.hour < 5) or (9 <= x.hour < 12))
    tp = (data["High"] + data["Low"] + data["Close"]) / 3
    vw = []; ct = cv = 0.0; pdd = None
    for i in range(len(data)):
        d = data["Date"].iloc[i]
        if d != pdd: ct = cv = 0.0; pdd = d
        if data["Volume"].iloc[i] > 0:
            ct += tp.iloc[i] * data["Volume"].iloc[i]; cv += data["Volume"].iloc[i]
        vw.append(ct / cv if cv > 0 else float("nan"))
    data["VWAP"] = vw
    dc = data[data.index.hour == 16][["Close"]].copy(); dc.index = dc.index.date
    dc = dc[~dc.index.duplicated(keep="last")]
    data["EMA50"] = data["Date"].map(dc["Close"].ewm(span=50).mean().to_dict())
    pc = data["Close"].shift(1)
    tr = pd.concat([data["High"]-data["Low"], (data["High"]-pc).abs(),
                    (data["Low"]-pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean(); data["HighVol"] = atr > 1.5 * atr.rolling(200).mean()
    data["SweepLow"] = (data["Low"] < data["AsianLow"]) & (data["Close"] > data["AsianLow"])
    cond = (data["SweepLow"] & data["InSession"] & (data["Close"] > data["VWAP"]) &
            (data["Close"] > data["EMA50"]) & ~data["HighVol"] & data["AsianLow"].notna())
    return bool(cond[data.tail(3).index].any()), float(data["Close"].iloc[-1])

def run_sweep_basket(broker, equity, open_syms, spy_bull, vix_mult):
    logger.info("SESSION SWEEP-BASKET start")
    print("\n-- S1 SWEEP BASKET (validated wider universe) --")
    if vix_mult == 0:
        print("  PAUSED (extreme VIX)"); return
    # Broker-specific universe: MT5/Pepperstone only offers a few of these as CFDs
    # (US single stocks aren't available), so restrict to what the broker actually
    # maps and skip the rest - avoids noisy caught "symbol not available" failures.
    # Alpaca (empty pass-through map) keeps the full validated universe.
    basket = SWEEP_BASKET
    if getattr(broker, "RESTRICTED_UNIVERSE", False):
        supported = set(getattr(broker, "SYMBOL_MAP", {}) or {})
        basket = [s for s in SWEEP_BASKET if s in supported]
        logger.info(f"sweep basket restricted to broker-supported: {basket}")
    for sym in basket:
        if sym in open_syms:
            print(f"  {sym}: already held, skip"); continue
        try:
            fires, price = _asian_sweep_fires(broker.get_bars(sym, "1Hour", 30))
        except Exception as e:
            logger.warning(f"sweep {sym} failed: {e}"); print(f"  {sym}: data err"); continue
        if fires:
            shares = round((equity * RISK_S1 * vix_mult * broker.RISK_SCALE) / (price * STOP_S1), 2)
            print(f"  SIGNAL {sym}: sweep below Asian low @ {price:.2f} -> BUY {shares}")
            broker.place_order_safe(sym, shares, "buy", "SWEEP")
        else:
            print(f"  {sym}: no signal")


# -- MAIN ----------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--session",
                    choices=["asian", "orb", "eod", "all", "btc", "rebal", "overnight", "btctrend", "sweep"], default=None)
parser.add_argument("--broker",
                    choices=["alpaca", "tradovate", "ctrader", "binance", "mt5"], default="alpaca",
                    help="Broker adapter to use (default: alpaca)")
parser.add_argument("--dry-run", action="store_true",
                    help="Print intended orders without placing them")
args = parser.parse_args()

if args.session is None:
    h = now_et().hour
    args.session = "asian" if 1 <= h < 7 else ("orb" if 10 <= h < 14 else "eod")

print(f"\n{'='*60}")
print(f"LIVE TRADER - broker={args.broker} dry_run={args.dry_run}")
print(f"  Session: {args.session.upper()} - {now_et().strftime('%Y-%m-%d %H:%M ET')}")
print(f"{'='*60}\n")
logger.info(f"START session={args.session} broker={args.broker} dry_run={args.dry_run}")

try:
    broker = make_broker(args.broker)
    if args.dry_run:
        broker = DryRunBroker(broker)
except Exception as e:
    logger.error(f"Broker init failed: {e}")
    alerts.send(f"BROKER INIT FAIL {args.broker}: {e}")
    print(f"ERROR: {e}")
    sys.exit(1)

equity    = broker.get_account()
open_syms = broker.get_positions()
vix_ma21, spy_bull, vix_mult, qqq_bear200 = get_regime()

# -- Conformal DD-throttle: scale RISK_SCALE by live drawdown headroom --
_throttle, _cur_dd, _peak, _month_pnl = update_risk_state(equity, args.broker)
broker.RISK_SCALE *= _throttle
logger.info(f"DD-throttle: peak=${_peak:,.0f} dd={_cur_dd:+.1%} "
            f"throttle={_throttle:.2f} -> RISK_SCALE={broker.RISK_SCALE:.2f} "
            f"| month P&L {_month_pnl:+.1%}")

# -- Worst-month guard: halt new orders if month-to-date loss breaches limit --
if _month_pnl <= -MONTHLY_KILL_PCT:
    msg = (f"MONTHLY KILL SWITCH: month-to-date {_month_pnl:.1%} exceeds limit "
           f"-{MONTHLY_KILL_PCT:.0%}. No new orders until next month.")
    logger.critical(msg); alerts.send(msg); print(f"\n{msg}\n")
    sys.exit(0)

# -- Kill-switch: daily loss check --
_risk_cfg = load_config("risk")
daily_start_equity = float(_risk_cfg.get("session_start_equity", str(equity)))
daily_pnl_pct = (equity - daily_start_equity) / max(daily_start_equity, 1)
if daily_pnl_pct <= -DAILY_KILL_PCT:
    msg = (f"KILL SWITCH: daily loss {daily_pnl_pct:.1%} exceeds limit "
           f"{DAILY_KILL_PCT:.0%}. No new orders.")
    logger.critical(msg); alerts.send(msg); print(f"\n{msg}\n")
    sys.exit(0)

print(f"Equity:     ${equity:,.2f}")
print(f"Broker:     {type(broker).__name__}  RISK_SCALE={broker.RISK_SCALE:.2f} "
      f"(DD-throttle {_throttle:.2f}, live DD {_cur_dd:+.1%})")
print(f"Regime:     VIX 21d={vix_ma21:.1f} | "
      f"SPY {'Golden [OK]' if spy_bull else 'Death [!]'} | "
      f"QQQ {'<200dSMA bear' if qqq_bear200 else '>200dSMA bull'}")
print(f"Positions:  {list(open_syms.keys()) or 'None'}")
print(f"Kill limit: daily loss {DAILY_KILL_PCT:.0%} | current {daily_pnl_pct:+.1%}")

if args.session == "asian":
    run_s1(broker, equity, open_syms, vix_ma21, spy_bull, vix_mult)
    run_s2(broker, equity, open_syms, vix_mult)
    run_s4(broker, equity, open_syms, spy_bull, vix_mult)
elif args.session == "orb":
    run_s5(broker, equity, open_syms, vix_ma21, spy_bull, qqq_bear200)
elif args.session == "eod":
    run_s3(broker, equity, open_syms, vix_mult)
elif args.session == "btc":
    run_btc(broker, equity, open_syms)
elif args.session == "rebal":
    run_xsmom(broker, equity, open_syms)
elif args.session == "overnight":
    run_overnight(broker, equity, open_syms)
elif args.session == "btctrend":
    run_btc_trend(broker, equity, open_syms)
elif args.session == "sweep":
    run_sweep_basket(broker, equity, open_syms, spy_bull, vix_mult)
elif args.session == "all":
    run_s1(broker, equity, open_syms, vix_ma21, spy_bull, vix_mult)
    run_s2(broker, equity, open_syms, vix_mult)
    run_s4(broker, equity, open_syms, spy_bull, vix_mult)
    run_s5(broker, equity, open_syms, vix_ma21, spy_bull, qqq_bear200)
    run_s3(broker, equity, open_syms, vix_mult)
    run_sweep_basket(broker, equity, open_syms, spy_bull, vix_mult)

print(f"\n{'='*60}")
print(f"Done - {now_et().strftime('%H:%M ET')}")
print(f"{'='*60}")
logger.info(f"END session={args.session}")
# FILL / DRY-RUN / kill-switch events alert on their own (broker.py). The
# per-session "complete" ping is demoted to a ONCE-DAILY heartbeat (17:0x ET)
# so a real signal is never buried under 24 hourly heartbeats.
if now_et().hour == 17:
    alerts.send(f"Daily heartbeat: session {args.session} ok | equity ${equity:,.2f}")
else:
    logger.info(f"Session {args.session} complete | equity ${equity:,.2f}")
