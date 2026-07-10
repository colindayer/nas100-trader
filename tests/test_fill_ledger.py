"""Deterministic verification for the fill ledger (no network, no brokers).

Covers: first write, append, duplicate-header prevention, missing values,
Alpaca-shaped record, MT5-shaped record, dry-run record, and the
never-crash-the-trader guarantee.

Run:  python3 tests/test_fill_ledger.py
"""
import csv
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

import fill_ledger                                   # noqa: E402
from broker import Broker, DryRunBroker              # noqa: E402

# redirect the ledger into a temp file for the whole test
TMP = tempfile.mkdtemp()
fill_ledger.LEDGER_PATH = os.path.join(TMP, "fills.csv")

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


def rows():
    with open(fill_ledger.LEDGER_PATH, newline="") as f:
        return list(csv.reader(f))


# ---- MT5-shaped fake (bracket-aware place_order, quote, LAST_FILL) ----------
class FakeMT5(Broker):
    ACCOUNT = "61552095"
    def quote(self, symbol):
        return (29788.1, 29790.3)
    def place_order(self, symbol, qty, side, tag, sl=None, tp=None):
        self.LAST_FILL = {"requested_price": 29790.3, "fill_price": 29790.5,
                          "order_id": 335999999, "position_id": 111222333}
        return 335999999


# ---- Alpaca-shaped fake (bracket place_order, fill price unknown yet) -------
class FakeAlpaca(Broker):
    ACCOUNT = "alpaca-paper"
    def quote(self, symbol):
        return (723.10, 723.14)
    def place_order(self, symbol, qty, side, tag, sl=None, tp=None):
        self.LAST_FILL = {"order_id": "abc-123", "fill_price": None}  # not filled yet
        return object()


# ---- broker with NO quote/fill info (missing values must stay empty) --------
class FakeBare(Broker):
    def place_order(self, symbol, qty, side, tag):   # no sl/tp support -> TypeError path
        self.LAST_FILL = {}
        return 1


fill_ledger.set_context(session="orb", account_equity=50000.02, risk_scale=1.0)

# 1. first write -> header + one row (MT5 record)
FakeMT5().place_order_safe("QQQ", 1.3, "buy", "S5",
                           sl=29492.0, tp=30683.0, signal_price=29789.6)
r = rows()
check("first write: header present", r[0] == fill_ledger.FIELDS)
check("first write: exactly 1 data row", len(r) == 2)
m = dict(zip(fill_ledger.FIELDS, r[1]))
check("MT5 record: broker/account/order/position", m["broker"] == "FakeMT5"
      and m["account"] == "61552095" and m["order_id"] == "335999999"
      and m["position_id"] == "111222333")
check("MT5 record: spread derived (2.2)", abs(float(m["spread"]) - 2.2) < 1e-6)
check("MT5 record: slippage vs signal (+0.9)", abs(float(m["slippage"]) - 0.9) < 1e-6)
check("MT5 record: stop/target recorded", m["stop_price"] == "29492" and m["target_price"] == "30683")
check("MT5 record: dry_run False, status submitted", m["dry_run"] == "False" and m["status"] == "submitted")
check("context fields present", m["session"] == "orb" and m["account_equity"] == "50000.02")

# 2. append (Alpaca record) -> no duplicate header
FakeAlpaca().place_order_safe("QQQ", 83, "buy", "S5",
                              sl=716.5, tp=745.5, signal_price=723.78)
r = rows()
check("append: 2 data rows", len(r) == 3)
check("duplicate header prevention", sum(1 for x in r if x == fill_ledger.FIELDS) == 1)
a = dict(zip(fill_ledger.FIELDS, r[2]))
check("Alpaca record: order id, EMPTY fill (not fabricated)",
      a["order_id"] == "abc-123" and a["fill_price"] == "" and a["slippage"] == "")
check("Alpaca record: bid/ask + spread_bps",
      a["bid_at_submission"] == "723.1" and float(a["spread_bps"]) > 0)

# 3. missing values (bare broker: no quote, no fills, no sl support)
FakeBare().place_order_safe("XYZ", 10, "sell", "S3")
b = dict(zip(fill_ledger.FIELDS, rows()[3]))
check("missing values stay empty (bid/ask/fill/signal/slippage/stop)",
      all(b[k] == "" for k in ("bid_at_submission", "ask_at_submission",
                               "fill_price", "signal_price", "slippage", "stop_price")))

# 4. dry-run record, clearly labeled
class _Alerts:                       # avoid real telegram in DryRun path
    pass
dry = DryRunBroker(FakeMT5())
dry.place_order_safe("QQQ", 1.3, "buy", "S1", sl=29492.0, tp=30683.0, signal_price=29789.6)
d = dict(zip(fill_ledger.FIELDS, rows()[4]))
check("dry-run: labeled dry_run=True status=dry_run",
      d["dry_run"] == "True" and d["status"] == "dry_run")
check("dry-run: inner broker quote captured", d["bid_at_submission"] == "29788.1")

# 5. failure path -> status=failed + error, order flow returns None w/o raising
class FakeBroken(Broker):
    def quote(self, symbol): return (None, None)
    def place_order(self, symbol, qty, side, tag, sl=None, tp=None):
        raise RuntimeError("synthetic reject")
import broker as _b
_b.time.sleep = lambda s: None       # no real backoff in tests
res = FakeBroken().place_order_safe("QQQ", 1, "buy", "S5", sl=1.0, tp=2.0, max_retries=2)
f = dict(zip(fill_ledger.FIELDS, rows()[5]))
check("failed order: status=failed + error captured, returns None",
      res is None and f["status"] == "failed" and "synthetic reject" in f["error"])

# 6. ledger failure NEVER crashes the trader (unwritable path)
fill_ledger.LEDGER_PATH = "/nonexistent-dir-xyz/fills.csv"
try:
    ok = FakeMT5().place_order_safe("QQQ", 1.3, "buy", "S5",
                                    sl=29492.0, tp=30683.0, signal_price=29789.6)
    check("ledger failure: order still succeeds", ok == 335999999)
except Exception as e:
    check(f"ledger failure: order still succeeds (raised {e})", False)

n_fail = sum(1 for _, ok in PASS if not ok)
print(f"\n{len(PASS)-n_fail}/{len(PASS)} checks passed")
sys.exit(1 if n_fail else 0)
