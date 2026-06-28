"""
broker.py — Abstract broker interface + DryRunBroker wrapper.

All broker adapters must subclass Broker and implement the five abstract methods.
Strategy logic in live_trader.py calls only these methods, never broker-specific APIs.
"""

import configparser
import logging
import os
import time

logger = logging.getLogger("trader")


def _load_local_csv(symbol: str, tf: str):
    """Fallback: read local CSV file (used by DryRunBroker when live API is unavailable)."""
    import pandas as pd, pytz as _tz
    eastern = _tz.timezone("US/Eastern")
    base = os.path.dirname(os.path.abspath(__file__))
    tf_tag = "hourly" if tf == "1Hour" else "1min"
    fname = os.path.join(base, f"{symbol.lower()}_{tf_tag}_7y.csv")
    if not os.path.exists(fname):
        raise FileNotFoundError(f"No local CSV for {symbol}/{tf}: {fname}")
    df = pd.read_csv(fname)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").tz_convert(eastern)
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol]
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def load_config(section: str) -> dict:
    """Read [section] from config.ini, then overlay any env vars named
    SECTION_KEY (e.g. ALPACA_KEY, CTRADER_CLIENT_ID). Env wins. This lets cloud
    deploys (GitHub Actions / Railway) inject credentials with no config.ini."""
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini"))
    d = dict(cfg[section]) if section in cfg else {}
    prefix = section.upper() + "_"
    for ek, ev in os.environ.items():
        if ek.startswith(prefix) and ev:
            d[ek[len(prefix):].lower()] = ev
    return d


class NotConfiguredError(RuntimeError):
    """Raised when a broker adapter finds placeholder credentials in config.ini."""
    pass


class Broker:
    SYMBOL_MAP: dict = {}
    RISK_SCALE: float = 1.0

    def map(self, symbol: str) -> str:
        return self.SYMBOL_MAP.get(symbol, symbol)

    def get_account(self) -> float:
        raise NotImplementedError

    def get_positions(self) -> dict:
        raise NotImplementedError

    def get_bars(self, symbol: str, tf: str, lookback: int):
        raise NotImplementedError

    def place_order(self, symbol: str, qty: float, side: str, tag: str):
        raise NotImplementedError

    def close_position(self, symbol: str):
        raise NotImplementedError

    def place_order_safe(self, symbol: str, qty: float, side: str, tag: str,
                         max_retries: int = 3):
        """Retry-with-backoff wrapper. Never double-sends on repeated failure."""
        import alerts
        for attempt in range(max_retries):
            try:
                result = self.place_order(symbol, qty, side, tag)
                logger.info(f"FILL {tag} {side.upper()} {qty:.1f} {symbol}")
                alerts.send(f"FILL {tag} {side.upper()} {qty:.1f} {symbol}")
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"ORDER_FAIL {tag} {symbol} after {max_retries} attempts: {e}")
                    alerts.send(f"ORDER FAIL {tag} {symbol}: {e}")
                    return None
                wait = 2 ** attempt
                logger.warning(f"Order attempt {attempt+1} failed ({e}), retrying in {wait}s")
                time.sleep(wait)


class DryRunBroker(Broker):
    """Wraps any broker; intercepts place_order + close_position and prints instead.

    get_account / get_positions fall back to safe defaults if the inner broker
    returns an auth error — so --dry-run works without valid live credentials.
    """

    _DEFAULT_EQUITY = 25_000.0  # assumed equity for sizing when API is unavailable

    def __init__(self, inner: Broker):
        self._b = inner
        self.SYMBOL_MAP = inner.SYMBOL_MAP
        self.RISK_SCALE = inner.RISK_SCALE

    def get_account(self) -> float:
        try:
            return self._b.get_account()
        except Exception as e:
            print(f"[DRY-RUN] get_account failed ({e}); using default ${self._DEFAULT_EQUITY:,.0f}")
            return self._DEFAULT_EQUITY

    def get_positions(self) -> dict:
        try:
            return self._b.get_positions()
        except Exception:
            return {}

    def get_bars(self, symbol: str, tf: str, lookback: int):
        try:
            return self._b.get_bars(symbol, tf, lookback)
        except Exception as e:
            print(f"[DRY-RUN] get_bars {symbol} failed ({type(e).__name__}); "
                  f"loading local CSV fallback")
            return _load_local_csv(symbol, tf)

    def place_order(self, symbol: str, qty: float, side: str, tag: str):
        msg = f"[DRY-RUN] WOULD {side.upper()} {qty:.1f} {symbol} ({tag})"
        print(msg)
        logger.info(msg)

    def close_position(self, symbol: str):
        msg = f"[DRY-RUN] WOULD close {symbol}"
        print(msg)
        logger.info(msg)

    def place_order_safe(self, symbol, qty, side, tag, max_retries=3):
        self.place_order(symbol, qty, side, tag)
