"""test_mt5_reconnect.py -- deterministic tests for MT5Broker mid-session reconnect.

Exercises the REAL mt5_broker methods against a fake MetaTrader5 module (no terminal).
Run:  ./.venv/bin/python test_mt5_reconnect.py

ROLLBACK: the reconnect fix is commits 54153e8 (reconnect guard) + this file's paired
place_order/close_position "connection down -> raise, no submit" guard. To roll back:
    git revert 54153e8
(then re-run py_compile + status.py + dashboard health as usual).

No strategy logic is touched by these tests.
"""
import logging
import time
import types
import unittest
from unittest import mock

import mt5_broker
from mt5_broker import MT5Broker

time.sleep = lambda *a, **k: None   # keep bounded-retry tests instant


def _res(ok=True):
    return types.SimpleNamespace(retcode=(0 if ok else 9), price=100.0, order=111, deal=222,
                                 comment="ok")


class FakeMT5:
    """Minimal MetaTrader5 stand-in with controllable drop/recover + call counters."""
    TRADE_ACTION_DEAL = 1; ORDER_TYPE_BUY = 0; ORDER_TYPE_SELL = 1
    ORDER_FILLING_IOC = 2; ORDER_TIME_GTC = 3; TRADE_RETCODE_DONE = 0
    POSITION_TYPE_BUY = 0; TIMEFRAME_H1 = 16

    def __init__(self, fail_reconnects=0, start_dropped=False):
        self.connected = not start_dropped
        self.fail_reconnects = fail_reconnects   # how many initialize() calls fail first
        self.reinit = 0
        self.order_send_calls = 0

    # health
    def terminal_info(self): return object() if self.connected else None
    def account_info(self):
        return types.SimpleNamespace(equity=100000.0, currency="USD") if self.connected else None

    # lifecycle
    def shutdown(self): pass
    def initialize(self, **kw):
        self.reinit += 1
        if self.fail_reconnects > 0:
            self.fail_reconnects -= 1
            self.connected = False
            return False
        self.connected = True
        return True

    # market/order
    def symbol_select(self, sym, sel=True): return True
    def symbol_info(self, sym):
        return types.SimpleNamespace(point=0.1, trade_stops_level=0, volume_min=0.01, volume_max=100.0)
    def symbol_info_tick(self, sym):
        return types.SimpleNamespace(ask=100.0, bid=99.9) if self.connected else None
    def positions_get(self, symbol=None):
        return [types.SimpleNamespace(ticket=1, volume=1.0, type=self.POSITION_TYPE_BUY,
                                      symbol="US100")] if self.connected else []
    def order_send(self, req):
        self.order_send_calls += 1
        return _res(ok=True)
    def last_error(self): return "fake error"


def make_broker(fake):
    """Build an MT5Broker WITHOUT running __init__ (no real terminal)."""
    b = object.__new__(MT5Broker)
    b._mt5 = fake
    b._login, b._passwd, b._server = "12345678", "SECRET_PW_123", "Broker-Server"
    b.RISK_SCALE = 1.0
    b.SYMBOL_MAP = {"QQQ": "US100", "SPY": "US500", "GLD": "XAUUSD", "BTC": "BTCUSD"}
    b._utc_off = 0.0
    return b


class ReconnectCases(unittest.TestCase):
    def test_1_healthy_no_reconnect(self):
        f = FakeMT5(start_dropped=False)
        b = make_broker(f)
        self.assertEqual(b.get_account(), 100000.0)
        self.assertEqual(f.reinit, 0, "healthy entry must not reinitialize")

    def test_2_dropped_first_reconnect_succeeds(self):
        f = FakeMT5(start_dropped=True, fail_reconnects=0)
        b = make_broker(f)
        self.assertEqual(b.get_account(), 100000.0)
        self.assertEqual(f.reinit, 1, "exactly one reinitialization")

    def test_3_two_fail_third_succeeds(self):
        f = FakeMT5(start_dropped=True, fail_reconnects=2)
        b = make_broker(f)
        self.assertEqual(b.get_account(), 100000.0, "method continues after recovery")
        self.assertEqual(f.reinit, 3, "bounded: recovered on the 3rd attempt")

    def test_4_all_fail_raises_no_order(self):
        f = FakeMT5(start_dropped=True, fail_reconnects=99)   # never recovers
        b = make_broker(f)
        with self.assertRaises(RuntimeError) as ctx:          # clear exception
            b.place_order("QQQ", 1.0, "buy", "S1", sl=95.0, tp=110.0)
        self.assertIn("not submitted", str(ctx.exception).lower())
        self.assertEqual(f.order_send_calls, 0, "NO order submitted when down")
        self.assertEqual(f.reinit, 3, "bounded retries (3), then give up")
        # crash-alert path reachable: a RuntimeError propagates to the caller/excepthook
        self.assertIsInstance(ctx.exception, RuntimeError)

    def test_5_place_order_during_reconnect_single_submit(self):
        f = FakeMT5(start_dropped=True, fail_reconnects=0)    # drop, recover on 1st try
        b = make_broker(f)
        oid = b.place_order("QQQ", 1.0, "buy", "S1", sl=95.0)
        self.assertEqual(f.reinit, 1, "reconnected once before submitting")
        self.assertEqual(f.order_send_calls, 1, "exactly one order_send after recovery")
        self.assertEqual(oid, 111)

    def test_6_close_position_during_reconnect_single_submit(self):
        f = FakeMT5(start_dropped=True, fail_reconnects=0)
        b = make_broker(f)
        b.close_position("QQQ")
        self.assertEqual(f.reinit, 1, "reconnected once before closing")
        self.assertEqual(f.order_send_calls, 1, "exactly one close submission after recovery")

    def test_7_credentials_never_logged(self):
        f = FakeMT5(start_dropped=True, fail_reconnects=1)
        b = make_broker(f)
        buf = []
        h = logging.Handler(); h.emit = lambda r: buf.append(r.getMessage())
        mt5_broker.logger.addHandler(h); mt5_broker.logger.setLevel(logging.DEBUG)
        with mock.patch("builtins.print") as p:
            b.get_account()
        mt5_broker.logger.removeHandler(h)
        blob = " ".join(buf) + " ".join(str(c) for c in p.call_args_list)
        self.assertNotIn("SECRET_PW_123", blob, "password must never be logged/printed")
        self.assertNotIn(b._passwd, blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
