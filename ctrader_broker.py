"""
ctrader_broker.py — FTMO / cTrader Open API adapter (scaffold).

Maps ETF symbols to CFD instruments. Reads from config.ini [ctrader].
RISK_SCALE = 1.0  (FTMO ~10% max DD fits our system at full size per FINDINGS.md)

The cTrader Open API uses protobuf over WebSocket — it requires:
  1. An OAuth application registered at https://openapi.ctrader.com
  2. A client_id + client_secret from that registration
  3. An access_token obtained via the OAuth flow for your trading account

SETUP REQUIRED before this adapter can be used. See SETUP.md → [ctrader] section.

This scaffold implements the full interface so live_trader.py can import and
instantiate it; all methods raise NotConfiguredError until credentials are set.
The REST-based Accounts API (v2) is used for account info to avoid requiring
the full WS stack for dry-run / read-only calls.
"""

import json
import logging
import os

import pandas as pd
import pytz
import requests

from broker import Broker, load_config, NotConfiguredError

logger = logging.getLogger("trader")
eastern = pytz.timezone("US/Eastern")

_PLACEHOLDER = {"YOUR_CTRADER_CLIENT_ID", "YOUR_CTRADER_CLIENT_SECRET",
                "YOUR_CTRADER_ACCESS_TOKEN", "-", ""}

# cTrader Open API REST v2 base (auth + account info only — order execution
# uses protobuf WebSocket which requires the ctrader-open-api Python library)
_REST_HOST = {
    "demo": "https://api.tradingstore.ctrader.com",
    "live": "https://api.ctrader.com",
}


class CTraderBroker(Broker):
    SYMBOL_MAP = {"QQQ": "US100", "GLD": "XAUUSD", "SPY": "US500"}
    RISK_SCALE = 1.0

    def __init__(self):
        cfg = load_config("ctrader")
        self._account_id    = cfg.get("account_id", "")
        self._client_id     = cfg.get("client_id", "")
        self._client_secret = cfg.get("client_secret", "")
        self._access_token  = cfg.get("access_token", "")
        host_key = cfg.get("host", "demo")
        self._base = _REST_HOST.get(host_key, _REST_HOST["demo"])
        self._check_configured()

    def _check_configured(self):
        bad = {self._client_id, self._client_secret, self._access_token} & _PLACEHOLDER
        if bad or not self._access_token:
            raise NotConfiguredError(
                "cTrader credentials not configured. See SETUP.md → [ctrader] section.\n"
                "You need to: (1) register an OAuth app at https://openapi.ctrader.com, "
                "(2) obtain an access_token via the OAuth flow, "
                "(3) fill in config.ini [ctrader]."
            )

    def _headers(self):
        return {"Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"}

    def get_account(self) -> float:
        self._check_configured()
        r = requests.get(
            f"{self._base}/connect/tradingaccounts/{self._account_id}",
            headers=self._headers(), timeout=15)
        r.raise_for_status()
        data = r.json()
        return float(data.get("balance", 0)) / 100.0  # cTrader stores cents

    def get_positions(self) -> dict:
        self._check_configured()
        r = requests.get(
            f"{self._base}/connect/tradingaccounts/{self._account_id}/positions",
            headers=self._headers(), timeout=15)
        r.raise_for_status()
        data = r.json()
        return {p["symbolName"]: p for p in data.get("position", [])}

    def get_bars(self, symbol: str, tf: str, lookback: int) -> pd.DataFrame:
        self._check_configured()
        # cTrader bar history endpoint (v2 REST)
        cfd = self.map(symbol)
        tf_map = {"1Hour": "H1", "1Min": "M1"}
        period = tf_map.get(tf, "H1")
        from datetime import datetime, timezone, timedelta
        end_ts   = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ts = int((datetime.now(timezone.utc) - timedelta(days=lookback)).timestamp() * 1000)
        r = requests.get(
            f"{self._base}/connect/tradingaccounts/{self._account_id}/symboltrendbars",
            headers=self._headers(), timeout=30,
            params={"symbolName": cfd, "period": period,
                    "fromTimestamp": start_ts, "toTimestamp": end_ts})
        r.raise_for_status()
        rows = r.json().get("data", [])
        if not rows:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").tz_convert(eastern)
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col] / 100_000.0  # cTrader stores price * 100000
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.columns = ["Open", "High", "Low", "Close", "Volume"]
        return df

    def place_order(self, symbol: str, qty: float, side: str, tag: str):
        self._check_configured()
        cfd = self.map(symbol)
        # Order execution via cTrader Open API requires the protobuf WebSocket.
        # The REST endpoint below is illustrative — real execution needs
        # the ctrader-open-api Python package (pip install ctrader-open-api).
        # See SETUP.md for the full WebSocket flow.
        order_type = "MARKET"
        body = {
            "symbolName": cfd,
            "tradeSide":  "BUY" if side.lower() == "buy" else "SELL",
            "volume":     int(qty * 100),  # cTrader volume in units (lot * 100)
            "orderType":  order_type,
            "label":      tag,
        }
        r = requests.post(
            f"{self._base}/connect/tradingaccounts/{self._account_id}/orders",
            headers=self._headers(), json=body, timeout=15)
        r.raise_for_status()
        resp = r.json()
        order_id = resp.get("orderId", "?")
        print(f"  {tag} {cfd}: {side.upper()} {qty:.1f} lots | order {order_id}")
        logger.info(f"ORDER {tag} {side.upper()} {qty:.1f} {cfd} id={order_id}")
        return resp

    def close_position(self, symbol: str):
        self._check_configured()
        cfd = self.map(symbol)
        positions = self.get_positions()
        if cfd not in positions:
            print(f"  {cfd}: no open position")
            return None
        pos = positions[cfd]
        pos_id = pos.get("positionId")
        volume = pos.get("volume", 0)
        r = requests.delete(
            f"{self._base}/connect/tradingaccounts/{self._account_id}/positions/{pos_id}",
            headers=self._headers(), timeout=15)
        r.raise_for_status()
        print(f"  CLOSE {cfd} (position {pos_id})")
        return r.json()
