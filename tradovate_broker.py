"""
tradovate_broker.py — Tradovate futures adapter (scaffold).

Maps ETF symbols to micro-futures contracts. Reads from config.ini [tradovate].
RISK_SCALE = 0.5  (tight trailing DD on futures evals → half-size per FINDINGS.md)

Point values: MNQ=$2/pt, MES=$5/pt, MGC=$10/pt
Qty passed to place_order() is CONTRACTS (not shares).

STATUS: scaffold — REST calls implemented, not yet live-tested.
Run `python tradovate_broker.py --test` to verify auth + account fetch.
See SETUP.md for credential setup.
"""

import json
import logging
import os
import time
import argparse
from datetime import datetime, timezone

import pandas as pd
import pytz
import requests

from broker import Broker, load_config, NotConfiguredError

logger = logging.getLogger("trader")
eastern = pytz.timezone("US/Eastern")

POINT_VALUES = {"MNQ": 2.0, "MES": 5.0, "MGC": 10.0}
_PLACEHOLDER = {"YOUR_TRADOVATE_USERNAME", "YOUR_TRADOVATE_PASSWORD",
                "YOUR_TRADOVATE_APP_ID", "YOUR_TRADOVATE_APP_SECRET"}


class TradovateBroker(Broker):
    SYMBOL_MAP = {"QQQ": "MNQ", "GLD": "MGC", "SPY": "MES"}
    RISK_SCALE = 0.5

    def __init__(self):
        cfg = load_config("tradovate")
        self._name   = cfg.get("name", "")
        self._pw     = cfg.get("password", "")
        self._app_id = cfg.get("app_id", "")
        self._app_secret = cfg.get("app_secret", "")
        base = cfg.get("base_url", "https://demo.tradovateapi.com/v1")
        self._base = base.rstrip("/")
        if {self._name, self._pw, self._app_id, self._app_secret} & _PLACEHOLDER or not self._name:
            raise NotConfiguredError(
                "Tradovate credentials missing. See SETUP.md → [tradovate] section.")
        self._token = None
        self._token_exp = 0.0
        self._contract_cache: dict = {}
        self._authenticate()

    def _authenticate(self):
        resp = requests.post(f"{self._base}/auth/accesstokenrequest", json={
            "name": self._name,
            "password": self._pw,
            "appId": self._app_id,
            "appVersion": "1.0",
            "cid": self._app_id,
            "sec": self._app_secret,
            "deviceId": "claude-trader",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["accessToken"]
        self._token_exp = time.time() + data.get("expirationTime", 3600 * 23)
        logger.info("Tradovate: authenticated")

    def _headers(self):
        if time.time() > self._token_exp - 60:
            self._authenticate()
        return {"Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json"}

    def _get(self, path: str) -> dict:
        r = requests.get(f"{self._base}/{path}", headers=self._headers(), timeout=15)
        if r.status_code == 401:
            self._authenticate()
            r = requests.get(f"{self._base}/{path}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        r = requests.post(f"{self._base}/{path}", headers=self._headers(),
                          json=body, timeout=15)
        if r.status_code == 401:
            self._authenticate()
            r = requests.post(f"{self._base}/{path}", headers=self._headers(),
                              json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    def _contract_id(self, name: str) -> int:
        if name not in self._contract_cache:
            data = self._get(f"contract/find?name={name}")
            self._contract_cache[name] = int(data["id"])
        return self._contract_cache[name]

    def get_account(self) -> float:
        accounts = self._get("account/list")
        return sum(float(a.get("balance", 0)) for a in accounts)

    def get_positions(self) -> dict:
        raw = self._get("position/list")
        result = {}
        for p in raw:
            sym = p.get("contractId")
            if sym and int(p.get("netPos", 0)) != 0:
                result[str(sym)] = p
        return result

    def get_bars(self, symbol: str, tf: str, lookback: int) -> pd.DataFrame:
        fut = self.map(symbol)
        cid = self._contract_id(fut)
        tf_map = {"1Hour": "1h", "1Min": "1m"}
        chart_tf = tf_map.get(tf, "1h")
        payload = {
            "symbol": fut,
            "contractId": cid,
            "chartDescription": {"underlyingType": "MinuteBar",
                                  "elementSize": 60 if tf == "1Hour" else 1,
                                  "withHistogram": False},
            "timeRange": {"asMuchAsElements": lookback * (24 if tf == "1Hour" else 24 * 60)},
        }
        data = self._post("md/getchart", payload)
        bars_raw = data.get("bars", [])
        if not bars_raw:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = pd.DataFrame(bars_raw)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").tz_convert(eastern)
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.columns = ["Open", "High", "Low", "Close", "Volume"]
        return df

    def place_order(self, symbol: str, qty: float, side: str, tag: str):
        fut = self.map(symbol)
        cid = self._contract_id(fut)
        contracts = max(1, int(round(qty)))
        action = "Buy" if side.lower() == "buy" else "Sell"
        body = {
            "accountSpec": self._name,
            "contractId": cid,
            "action": action,
            "orderQty": contracts,
            "orderType": "Market",
            "isAutomated": True,
        }
        resp = self._post("order/placeorder", body)
        order_id = resp.get("orderId", "?")
        print(f"  {tag} {fut}: {action} {contracts} contracts | order {order_id}")
        logger.info(f"ORDER {tag} {action} {contracts} {fut} id={order_id}")
        return resp

    def close_position(self, symbol: str):
        fut = self.map(symbol)
        cid = self._contract_id(fut)
        positions = self.get_positions()
        pos = next((p for p in positions.values()
                    if p.get("contractId") == cid), None)
        if pos is None:
            print(f"  {fut}: no open position")
            return None
        net = int(pos.get("netPos", 0))
        if net == 0:
            return None
        action = "Sell" if net > 0 else "Buy"
        body = {
            "accountSpec": self._name,
            "contractId": cid,
            "action": action,
            "orderQty": abs(net),
            "orderType": "Market",
            "isAutomated": True,
        }
        resp = self._post("order/placeorder", body)
        print(f"  CLOSE {fut} ({net} contracts) | {resp.get('orderId')}")
        return resp


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Verify auth + account fetch")
    args = parser.parse_args()
    if args.test:
        broker = TradovateBroker()
        equity = broker.get_account()
        print(f"Tradovate account equity: ${equity:,.2f}")
        pos = broker.get_positions()
        print(f"Open positions: {pos}")
