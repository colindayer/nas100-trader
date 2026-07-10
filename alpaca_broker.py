"""
alpaca_broker.py — Alpaca paper/live adapter for ETF strategies.

Reads credentials from config.ini [alpaca] section.
RISK_SCALE = 1.0  (full sizing — Alpaca paper account / FTMO-equivalent DD limits)
"""

import os
import pandas as pd
import pytz
from datetime import datetime, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (MarketOrderRequest, StopLossRequest,
                                     TakeProfitRequest)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from broker import Broker, load_config, NotConfiguredError

eastern = pytz.timezone("US/Eastern")
_TF_MAP = {"1Hour": TimeFrame.Hour, "1Min": TimeFrame.Minute,
           "1Day": TimeFrame.Day}


class AlpacaBroker(Broker):
    SYMBOL_MAP = {}   # ETF symbols pass through unchanged
    RISK_SCALE = 1.0

    def __init__(self):
        cfg = load_config("alpaca")
        key    = cfg.get("key", "")
        secret = cfg.get("secret", "")
        key    = os.environ.get("ALPACA_KEY",    key)
        secret = os.environ.get("ALPACA_SECRET", secret)
        if not key or key.startswith("YOUR_"):
            raise NotConfiguredError(
                "Alpaca credentials missing. See SETUP.md → [alpaca] section.")
        # Default to PAPER (safe). Only goes live if base_url is explicitly the
        # live endpoint. In the cloud with no base_url set, this stays paper.
        base_url = cfg.get("base_url", "https://paper-api.alpaca.markets")
        paper = "paper" in base_url
        self._trade  = TradingClient(key, secret, paper=paper)
        self._data   = StockHistoricalDataClient(key, secret)
        self.ACCOUNT = "alpaca-paper" if paper else "alpaca-LIVE"   # ledger label

    def quote(self, symbol: str):
        """(bid, ask) for the fill ledger. Read-only; never raises."""
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            q = self._data.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
            bid, ask = float(q.bid_price or 0), float(q.ask_price or 0)
            return (bid or None, ask or None)
        except Exception:
            return (None, None)

    def get_account(self) -> float:
        return float(self._trade.get_account().equity)

    def get_positions(self) -> dict:
        return {p.symbol: p for p in self._trade.get_all_positions()}

    def get_bars(self, symbol: str, tf: str, lookback: int) -> pd.DataFrame:
        alpaca_tf = _TF_MAP.get(tf)
        if alpaca_tf is None:
            raise ValueError(f"Unsupported timeframe '{tf}'. Use '1Hour' or '1Min'.")
        # CONTRACT: lookback = number of BARS (same as MT5/Binance adapters).
        # This adapter used to read it as DAYS, so the same call returned ~16x
        # more history on Alpaca than on MT5 — strategies behaved differently
        # per venue (MT5's EMA50/HighVol filters were starved). Fetch a generous
        # calendar window, then trim to the last `lookback` bars.
        if tf == "1Day":
            days = int(lookback * 1.6) + 10
        elif tf == "1Hour":
            days = int(lookback / 10) + 10       # ~16 ext-hours bars/trading day
        else:  # 1Min
            days = int(lookback / 600) + 5
        start = datetime.now(pytz.utc) - timedelta(days=days)
        req   = StockBarsRequest(symbol_or_symbols=[symbol],
                                  timeframe=alpaca_tf, start=start)
        bars = self._data.get_stock_bars(req).df
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level="symbol")
        bars.index = pd.to_datetime(bars.index, utc=True).tz_convert(eastern)
        bars = bars[["open", "high", "low", "close", "volume"]].copy()
        bars.columns = ["Open", "High", "Low", "Close", "Volume"]
        return bars.tail(lookback)

    def place_order(self, symbol: str, qty: float, side: str, tag: str,
                    sl: float = None, tp: float = None):
        if qty < 1:
            print(f"  {tag} {symbol}: qty < 1, skip")
            return None
        # Broker-side protection: BRACKET (sl+tp) or OTO stop-only, so the position
        # is protected even if the bot/runner dies. Falls back to a plain market
        # order only when no sl was provided (state-machine/time-exit strategies).
        # GTC, not DAY: the validated backtests hold every position to its stop or
        # target ACROSS days. DAY brackets expire at the close, leaving the position
        # open but unprotected and never target-exited — a live/backtest divergence.
        kwargs = dict(
            symbol=symbol,
            qty=int(qty),
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
        )
        note = ""
        if sl is not None:
            kwargs["stop_loss"] = StopLossRequest(stop_price=round(sl, 2))
            if tp is not None:
                kwargs["order_class"] = OrderClass.BRACKET
                kwargs["take_profit"] = TakeProfitRequest(limit_price=round(tp, 2))
                note = f" SL={sl:.2f} TP={tp:.2f}"
            else:
                kwargs["order_class"] = OrderClass.OTO
                note = f" SL={sl:.2f}"
        order = self._trade.submit_order(MarketOrderRequest(**kwargs))
        # fill-ledger details (logging only). filled_avg_price is usually None at
        # submission for market orders -> empty field, never fabricated.
        fap = getattr(order, "filled_avg_price", None)
        self.LAST_FILL = {"order_id": str(order.id),
                          "fill_price": float(fap) if fap else None}
        print(f"  {tag} {symbol}: {side.upper()} {int(qty)} shares{note} | {order.id}")
        return order

    def close_position(self, symbol: str):
        positions = self.get_positions()
        if symbol not in positions:
            print(f"  {symbol}: no open position to close")
            return None
        pos = positions[symbol]
        qty = abs(int(float(pos.qty)))
        order = self._trade.submit_order(MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        ))
        print(f"  CLOSE {symbol} | {order.id}")
        return order
