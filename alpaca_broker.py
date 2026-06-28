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
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from broker import Broker, load_config, NotConfiguredError

eastern = pytz.timezone("US/Eastern")
_TF_MAP = {"1Hour": TimeFrame.Hour, "1Min": TimeFrame.Minute}


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

    def get_account(self) -> float:
        return float(self._trade.get_account().equity)

    def get_positions(self) -> dict:
        return {p.symbol: p for p in self._trade.get_all_positions()}

    def get_bars(self, symbol: str, tf: str, lookback: int) -> pd.DataFrame:
        alpaca_tf = _TF_MAP.get(tf)
        if alpaca_tf is None:
            raise ValueError(f"Unsupported timeframe '{tf}'. Use '1Hour' or '1Min'.")
        start = datetime.now(pytz.utc) - timedelta(days=lookback)
        req   = StockBarsRequest(symbol_or_symbols=[symbol],
                                  timeframe=alpaca_tf, start=start)
        bars = self._data.get_stock_bars(req).df
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level="symbol")
        bars.index = pd.to_datetime(bars.index, utc=True).tz_convert(eastern)
        bars = bars[["open", "high", "low", "close", "volume"]].copy()
        bars.columns = ["Open", "High", "Low", "Close", "Volume"]
        return bars

    def place_order(self, symbol: str, qty: float, side: str, tag: str):
        if qty < 1:
            print(f"  {tag} {symbol}: qty < 1, skip")
            return None
        order = self._trade.submit_order(MarketOrderRequest(
            symbol=symbol,
            qty=int(qty),
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        ))
        print(f"  {tag} {symbol}: {side.upper()} {int(qty)} shares | {order.id}")
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
