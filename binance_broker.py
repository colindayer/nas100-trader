"""
binance_broker.py — Binance spot adapter for the BTC sweep pillar.

- get_bars uses the PUBLIC klines endpoint (no auth) → works in --dry-run.
- get_account / get_positions / place_order / close_position use SIGNED endpoints
  (HMAC-SHA256) and require [binance] key+secret in config.ini.

Crypto trades on its own account (no prop trailing-DD), so RISK_SCALE defaults to
1.0 — override in config if you want smaller crypto sizing. Validated edge: BTC
Asian sweep (see FINDINGS.md — pillar #3, uncorrelated to Nasdaq/gold).

NOTE: this is the EXECUTION layer. Wiring the BTC sweep *signals* into live_trader
(a run_btc() that calls this adapter) is a separate step — see STATUS/SETUP.
"""
import hashlib
import hmac
import logging
import time
import urllib.parse
import urllib.request
import json

import pandas as pd

from broker import Broker, load_config, NotConfiguredError

logger = logging.getLogger("trader")

_PLACEHOLDER = {"YOUR_BINANCE_KEY", "YOUR_BINANCE_SECRET", "", "-"}
_TF = {"1Min": "1m", "5Min": "5m", "15Min": "15m", "1Hour": "1h",
       "1H": "1h", "1Day": "1d", "1D": "1d"}


class BinanceBroker(Broker):
    # Internal symbol → Binance symbol. The BTC sweep uses "BTC".
    SYMBOL_MAP = {"BTC": "BTCUSDT", "BTCUSD": "BTCUSDT", "ETH": "ETHUSDT"}
    RISK_SCALE = 1.0

    def __init__(self):
        cfg = load_config("binance")
        self._key    = cfg.get("key", "")
        self._secret = cfg.get("secret", "")
        self._base   = cfg.get("base_url", "https://api.binance.com")
        try:
            self.RISK_SCALE = float(cfg.get("risk_scale", "1.0"))
        except ValueError:
            self.RISK_SCALE = 1.0
        self._authed = self._key not in _PLACEHOLDER and self._secret not in _PLACEHOLDER

    # ── helpers ───────────────────────────────────────────────────────────────
    def _require_auth(self):
        if not self._authed:
            raise NotConfiguredError(
                "Binance key/secret not set in config.ini [binance] — "
                "create API keys at binance.com (Spot trading enabled).")

    def _signed_request(self, method: str, path: str, params: dict):
        self._require_auth()
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urllib.parse.urlencode(params)
        sig = hmac.new(self._secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{self._base}{path}?{query}&signature={sig}"
        req = urllib.request.Request(url, method=method,
                                     headers={"X-MBX-APIKEY": self._key})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())

    # ── public market data (works without auth → dry-run) ─────────────────────
    def get_bars(self, symbol: str, tf: str, lookback: int):
        sym = self.map(symbol)
        interval = _TF.get(tf, "1h")
        url = (f"{self._base}/api/v3/klines?symbol={sym}"
               f"&interval={interval}&limit={min(lookback, 1000)}")
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            df = pd.DataFrame(data, columns=["ot", "Open", "High", "Low", "Close",
                                             "Volume", "ct", "qv", "n", "tb", "tq", "ig"])
            df.index = pd.to_datetime(df["ot"], unit="ms", utc=True)
            return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        except Exception as e:
            # Binance geo-blocks US cloud IPs (HTTP 451). Fall back to yfinance
            # (BTC-USD) so BTC data works ANYWHERE (cloud/US) for dry-run/signals.
            logger.warning(f"Binance get_bars failed ({e}); yfinance fallback")
            import yfinance as yf
            yf_sym = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}.get(sym, sym)
            yf_int = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d"}.get(interval, "1h")
            period = "60d" if yf_int.endswith("m") else ("730d" if yf_int == "1h" else "max")
            d = yf.download(yf_sym, period=period, interval=yf_int, progress=False, auto_adjust=True)
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d = d[["Open", "High", "Low", "Close", "Volume"]].dropna().tail(min(lookback, 1000))
            if d.index.tz is None:
                d.index = d.index.tz_localize("UTC")
            return d

    # ── account / positions ───────────────────────────────────────────────────
    def get_account(self) -> float:
        """USDT balance (quote-currency equity proxy)."""
        acct = self._signed_request("GET", "/api/v3/account", {})
        for b in acct.get("balances", []):
            if b["asset"] == "USDT":
                return float(b["free"]) + float(b["locked"])
        return 0.0

    def get_positions(self) -> dict:
        acct = self._signed_request("GET", "/api/v3/account", {})
        out = {}
        for b in acct.get("balances", []):
            amt = float(b["free"]) + float(b["locked"])
            if amt > 0 and b["asset"] not in ("USDT", "USDC", "BUSD"):
                out[b["asset"]] = amt
        return out

    # ── orders ────────────────────────────────────────────────────────────────
    def place_order(self, symbol: str, qty: float, side: str, tag: str):
        sym = self.map(symbol)
        qty = round(float(qty), 5)
        params = {"symbol": sym, "side": side.upper(), "type": "MARKET",
                  "quantity": qty, "newClientOrderId": f"{tag}-{int(time.time())}"}
        res = self._signed_request("POST", "/api/v3/order", params)
        logger.info(f"BINANCE FILL {tag} {side} {qty} {sym} id={res.get('orderId')}")
        return res.get("orderId")

    def close_position(self, symbol: str):
        sym = self.map(symbol)
        base_asset = sym.replace("USDT", "")
        held = self.get_positions().get(base_asset, 0.0)
        if held > 0:
            return self.place_order(symbol, held, "sell", "CLOSE")
        return None
