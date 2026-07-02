"""
mt5_broker.py — MetaTrader 5 adapter (for FTMO / prop accounts via MT5).

Runs on WINDOWS (the `MetaTrader5` package is Windows-only). Use an instant MT5
DEMO account first — no KYC — to verify sizing + execution before any real money.

Maps the validated pillars to CFD symbols:
    QQQ → US100   (Nasdaq-100, validated to port — see cfd_validate.py)
    SPY → US500
    GLD → XAUUSD  (gold, validated to port)
⚠️ Symbol names vary by broker. If get_bars fails, run `python mt5_broker.py`
   to print the exact symbols your broker uses, then set [mt5] map_* in config.

Sizing: live_trader computes `qty` in INSTRUMENT UNITS from the instrument's own
price (get_bars returns real MT5 prices), so % risk is preserved. We convert
units → lots via the symbol's contract size, round to volume_step, clamp to
[volume_min, volume_max]. VERIFY the printed lot sizes on demo before going live.

config.ini [mt5]:
    login    = 12345678
    password = ...
    server   = MetaQuotes-Demo        (or FTMO-Demo / your broker's server)
    map_qqq  = US100        (optional overrides if your broker names differ)
    map_spy  = US500
    map_gld  = XAUUSD
"""
import logging
import pandas as pd
import pytz

from broker import Broker, load_config, NotConfiguredError

logger = logging.getLogger("trader")
eastern = pytz.timezone("US/Eastern")


class MT5Broker(Broker):
    SYMBOL_MAP = {"QQQ": "US100", "SPY": "US500", "GLD": "XAUUSD", "BTC": "BTCUSD"}
    RISK_SCALE = 1.0

    def __init__(self):
        try:
            import MetaTrader5 as mt5
        except ImportError as e:
            raise NotConfiguredError(
                "MetaTrader5 package not installed (Windows only). "
                "On the VPS: pip install MetaTrader5") from e
        self._mt5 = mt5
        cfg = load_config("mt5")
        # optional per-broker symbol overrides
        for internal in ("qqq", "spy", "gld", "btc"):
            ov = cfg.get(f"map_{internal}")
            if ov:
                self.SYMBOL_MAP[internal.upper()] = ov
        login  = cfg.get("login", "")
        passwd = cfg.get("password", "")
        server = cfg.get("server", "")
        if not login or login.startswith("YOUR_"):
            raise NotConfiguredError(
                "MT5 credentials missing. Set [mt5] login/password/server in config.ini.")
        ok = mt5.initialize(login=int(login), password=passwd, server=server)
        if not ok:
            raise NotConfiguredError(f"MT5 initialize failed: {mt5.last_error()}")
        info = mt5.account_info()
        logger.info(f"MT5 connected: login={login} server={server} "
                    f"equity={getattr(info, 'equity', '?')} "
                    f"currency={getattr(info, 'currency', '?')}")
        # MT5 bar/tick timestamps are in SERVER time (brokers run "NY-close"
        # charts, UTC+2 winter / UTC+3 summer), NOT UTC. Treating them as UTC
        # shifts every session window ~3h and corrupts Asian high/low & ORB.
        self._utc_off = self._detect_utc_offset(float(cfg.get("server_utc_offset", "3")))
        logger.info(f"MT5 server-UTC offset: {self._utc_off:+.0f}h "
                    f"(bars re-based to true UTC)")

    def _detect_utc_offset(self, fallback):
        """Compare a live tick's server timestamp to real UTC. Only trust the
        detection if the tick is fresh (market open); else use config/fallback."""
        import time as _time
        m = self._mt5
        for probe in ("BTCUSD", "US100", "XAUUSD", "EURUSD"):
            try:
                if not m.symbol_select(probe, True):
                    continue
                tick = m.symbol_info_tick(probe)
                if tick is None or not tick.time:
                    continue
                diff_h = (tick.time - _time.time()) / 3600.0
                off = round(diff_h)
                # fresh tick: residual under ~5 min after removing whole hours
                if abs(diff_h - off) < 0.084 and -12 <= off <= 14:
                    return float(off)
            except Exception:
                continue
        return fallback

    _TF = None
    def _tf(self, tf):
        m = self._mt5
        table = {"1Min": m.TIMEFRAME_M1, "1Hour": m.TIMEFRAME_H1, "1Day": m.TIMEFRAME_D1}
        if tf not in table:
            raise ValueError(f"Unsupported timeframe '{tf}'")
        return table[tf]

    def _ensure_symbol(self, sym):
        if not self._mt5.symbol_select(sym, True):
            raise ValueError(f"Symbol '{sym}' not available on this broker "
                             f"(run `python mt5_broker.py` to list valid symbols)")

    def get_account(self) -> float:
        info = self._mt5.account_info()
        if info is None:
            raise RuntimeError(f"MT5 account_info failed: {self._mt5.last_error()}")
        return float(info.equity)

    def get_positions(self) -> dict:
        out = {}
        for p in (self._mt5.positions_get() or []):
            # reverse-map CFD symbol back to internal ticker where possible
            internal = next((k for k, v in self.SYMBOL_MAP.items() if v == p.symbol), p.symbol)
            out[internal] = p
        return out

    def get_bars(self, symbol: str, tf: str, lookback: int) -> pd.DataFrame:
        sym = self.map(symbol)
        self._ensure_symbol(sym)
        rates = self._mt5.copy_rates_from_pos(sym, self._tf(tf), 0, lookback)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"MT5 get_bars {sym} failed: {self._mt5.last_error()}")
        df = pd.DataFrame(rates)
        # rebase server-time epoch → true UTC before converting to ET
        utc_secs = df["time"] - self._utc_off * 3600
        df.index = pd.to_datetime(utc_secs, unit="s", utc=True).dt.tz_convert(eastern)
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                "close": "Close", "tick_volume": "Volume"})
        return df[["Open", "High", "Low", "Close", "Volume"]]

    def _units_to_lots(self, sym, units):
        info = self._mt5.symbol_info(sym)
        cs = getattr(info, "trade_contract_size", 1.0) or 1.0
        lots = abs(units) / cs
        step = getattr(info, "volume_step", 0.01) or 0.01
        lots = round(lots / step) * step
        lots = max(getattr(info, "volume_min", 0.01), min(lots, getattr(info, "volume_max", 100.0)))
        return round(lots, 2)

    def place_order(self, symbol: str, qty: float, side: str, tag: str):
        m = self._mt5; sym = self.map(symbol); self._ensure_symbol(sym)
        lots = self._units_to_lots(sym, qty)
        tick = m.symbol_info_tick(sym)
        price = tick.ask if side.lower() == "buy" else tick.bid
        req = {
            "action": m.TRADE_ACTION_DEAL, "symbol": sym, "volume": lots,
            "type": m.ORDER_TYPE_BUY if side.lower() == "buy" else m.ORDER_TYPE_SELL,
            "price": price, "deviation": 20, "magic": 770001,
            "comment": tag, "type_filling": m.ORDER_FILLING_IOC,
            "type_time": m.ORDER_TIME_GTC,
        }
        res = m.order_send(req)
        if res is None or res.retcode != m.TRADE_RETCODE_DONE:
            rc = getattr(res, "retcode", "?"); cm = getattr(res, "comment", m.last_error())
            logger.error(f"MT5 ORDER FAIL {tag} {sym} {side} {lots}: retcode={rc} {cm}")
            raise RuntimeError(f"MT5 order failed retcode={rc}: {cm}")
        logger.info(f"MT5 FILL {tag} {side} {lots} lots {sym} @ {res.price} ticket={res.order}")
        return res.order

    def close_position(self, symbol: str):
        m = self._mt5; sym = self.map(symbol)
        positions = [p for p in (m.positions_get(symbol=sym) or [])]
        if not positions:
            print(f"  {sym}: no open position to close"); return None
        last = None
        for p in positions:
            tick = m.symbol_info_tick(sym)
            is_buy = p.type == m.POSITION_TYPE_BUY
            req = {
                "action": m.TRADE_ACTION_DEAL, "symbol": sym, "volume": p.volume,
                "type": m.ORDER_TYPE_SELL if is_buy else m.ORDER_TYPE_BUY,
                "position": p.ticket, "price": tick.bid if is_buy else tick.ask,
                "deviation": 20, "magic": 770001, "comment": "CLOSE",
                "type_filling": m.ORDER_FILLING_IOC, "type_time": m.ORDER_TIME_GTC,
            }
            res = m.order_send(req)
            logger.info(f"MT5 CLOSE {sym} ticket={p.ticket} retcode={getattr(res,'retcode','?')}")
            last = res
        return last


# ── diagnostic: run directly on the VPS to discover symbols + verify connection ──
if __name__ == "__main__":
    b = MT5Broker()
    print(f"\nConnected. Equity: {b.get_account():,.2f}")
    print("\nSearching for your broker's symbol names (Nasdaq / S&P / gold):")
    m = b._mt5
    for needle in ("100", "NAS", "US500", "SPX", "XAU", "GOLD"):
        hits = [s.name for s in m.symbols_get() if needle in s.name.upper()][:8]
        if hits:
            print(f"  match '{needle}': {hits}")
    print("\nIf US100/US500/XAUUSD aren't exact, set [mt5] map_qqq/map_spy/map_gld in config.ini.")
    for internal in ("QQQ", "GLD"):
        try:
            bars = b.get_bars(internal, "1Hour", 3)
            print(f"  {internal}->{b.map(internal)}: last close {bars['Close'].iloc[-1]}")
        except Exception as e:
            print(f"  {internal}->{b.map(internal)}: {e}")
