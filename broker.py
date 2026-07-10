"""
broker.py — Abstract broker interface + DryRunBroker wrapper.

All broker adapters must subclass Broker and implement the five abstract methods.
Strategy logic in live_trader.py calls only these methods, never broker-specific APIs.
"""

import configparser
import logging
import os
import time
import json
from datetime import datetime, timezone

logger = logging.getLogger("trader")


def _load_local_csv(symbol: str, tf: str):
    """Fallback: read local CSV file (used by DryRunBroker when live API is unavailable)."""
    import pandas as pd, pytz as _tz
    eastern = _tz.timezone("US/Eastern")
    base = os.path.dirname(os.path.abspath(__file__))
    tf_map = {"1Min": "1min", "1Hour": "hourly", "1Day": "daily"}
    tf_tag = tf_map.get(tf, "1min")
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

    # --- read-only introspection for the fill ledger (logging only) ----------
    ACCOUNT: str = ""          # adapters may set a label (login id / "paper")
    LAST_FILL: dict = {}       # adapters may stash fill details after success

    def quote(self, symbol: str):
        """(bid, ask) at submission time, or (None, None) if unavailable.
        Read-only; adapters override. Must never raise."""
        return (None, None)

    def _ledger(self, **kw):
        """Record a fill-ledger row. NEVER raises, never affects the order."""
        try:
            import fill_ledger
            fill_ledger.record(broker=type(self).__name__,
                               account=getattr(self, "ACCOUNT", ""), **kw)
        except Exception:
            pass

    def place_order_safe(self, symbol: str, qty: float, side: str, tag: str,
                         max_retries: int = 3, sl: float = None, tp: float = None,
                         signal_price: float = None, signal_ts: str = None):
        """Retry-with-backoff wrapper. Never double-sends on repeated failure.
        sl/tp are absolute PRICE levels attached broker-side at entry, so the stop
        is enforced by the broker even if the bot/VPS goes offline. Brokers that
        don't support brackets fall back to a plain order.
        signal_price/signal_ts are LOGGING-ONLY passthroughs for the fill ledger
        (the research's assumed entry) -- they influence nothing."""
        import alerts
        if sl is None:
            logger.warning(f"NAKED ORDER {tag} {symbol} - no stop-loss attached")
        brk = f" SL={sl:.2f} TP={tp:.2f}" if sl is not None else " (no SL)"
        try:
            bid, ask = self.quote(symbol)
        except Exception:
            bid, ask = (None, None)
        for attempt in range(max_retries):
            try:
                try:
                    result = self.place_order(symbol, qty, side, tag, sl=sl, tp=tp)
                except TypeError:
                    result = self.place_order(symbol, qty, side, tag)
                logger.info(f"FILL {tag} {side.upper()} {qty:.1f} {symbol}{brk}")
                alerts.send(f"FILL {tag} {side.upper()} {qty:.1f} {symbol}{brk}")
                lf = getattr(self, "LAST_FILL", {}) or {}
                self._ledger(strategy=tag, symbol=symbol, side=side, quantity=qty,
                             signal_price=signal_price, signal_timestamp=signal_ts or "",
                             bid_at_submission=bid, ask_at_submission=ask,
                             requested_price=lf.get("requested_price"),
                             fill_price=lf.get("fill_price"),
                             stop_price=sl, target_price=tp,
                             order_id=lf.get("order_id", result if result is not None else ""),
                             position_id=lf.get("position_id"),
                             dry_run="False", status="submitted")
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"ORDER_FAIL {tag} {symbol} after {max_retries} attempts: {e}")
                    alerts.send(f"ORDER FAIL {tag} {symbol}: {e}")
                    self._ledger(strategy=tag, symbol=symbol, side=side, quantity=qty,
                                 signal_price=signal_price, signal_timestamp=signal_ts or "",
                                 bid_at_submission=bid, ask_at_submission=ask,
                                 stop_price=sl, target_price=tp,
                                 dry_run="False", status="failed", error=str(e)[:200])
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
            eq = self._b.get_account()
            if not eq or eq <= 0:
                # unfunded / unauthenticated account returns 0 → use notional default
                print(f"[DRY-RUN] inner equity ${eq:,.2f}; using default ${self._DEFAULT_EQUITY:,.0f}")
                return self._DEFAULT_EQUITY
            return eq
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

    def place_order_safe(self, symbol, qty, side, tag, max_retries=3, sl=None, tp=None,
                         signal_price=None, signal_ts=None):
        import alerts
        brk = f" SL={sl:.2f} TP={tp:.2f}" if sl is not None else " (no SL)"
        self.place_order(symbol, qty, side, tag)
        print(f"[DRY-RUN] brackets:{brk}")
        alerts.send(
            f"DRY RUN {tag}\n"
            f"{side.upper()} {qty:.5f} {symbol}{brk}"
        )
        # ledger row, clearly labeled dry-run (logging only, never raises)
        try:
            bid, ask = self._b.quote(symbol)
        except Exception:
            bid, ask = (None, None)
        self._ledger(strategy=tag, symbol=symbol, side=side, quantity=qty,
                     signal_price=signal_price, signal_timestamp=signal_ts or "",
                     bid_at_submission=bid, ask_at_submission=ask,
                     stop_price=sl, target_price=tp,
                     dry_run="True", status="dry_run")
