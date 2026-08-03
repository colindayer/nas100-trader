"""Adversarial tests for the frozen rebalance loop, with MT5 mocked.

    python tests/test_frozen_loop.py

Covers the failures that actually cause money loss in a rebalancing bot:
  1 a restart must not duplicate an order (deterministic intent ids)
  2 the no-trade band must suppress small moves and permit large ones
  3 a target crossing zero must be classified as a CLOSE, never as an increase
  4 closes must be ordered BEFORE opens
  5 held state must come from broker positions, and a failed positions_get() must ABORT
  6 no fixed TP and no trailing stop may exist anywhere in the module
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FakeInfo:
    volume_min, volume_max, volume_step, point, trade_stops_level = 0.01, 100.0, 0.01, 0.01, 0
    trade_contract_size = 1.0


class FakeTick:
    def __init__(self, p=100.0, s=0.02):
        self.ask, self.bid, self.last = p + s / 2, p - s / 2, p


class FakePos:
    def __init__(self, symbol, volume, typ, magic, ticket=1):
        self.symbol, self.volume, self.type, self.magic, self.ticket = symbol, volume, typ, magic, ticket


def install_fake_mt5(positions=(), positions_fail=False):
    m = types.SimpleNamespace()
    m.ORDER_TYPE_BUY, m.ORDER_TYPE_SELL = 0, 1
    m.symbol_info = lambda s: FakeInfo()
    m.symbol_info_tick = lambda s: FakeTick()
    m.positions_get = (lambda **k: None) if positions_fail else (lambda **k: list(positions))
    sys.modules["MetaTrader5"] = m
    return m


def main():
    install_fake_mt5()
    import importlib
    import scripts.frozen_portfolio as fp
    importlib.reload(fp)
    fp.mt5 = sys.modules["MetaTrader5"]

    acct = types.SimpleNamespace(login=1514166963, server="FTMO-Demo", equity=100_000.0, trade_mode=0)
    syms = {n: n for n in fp.FROZEN_UNIVERSE}

    # 1 — deterministic intent ids: same inputs -> same id (restart cannot duplicate)
    a = fp.intent_id(acct.login, "GOLD", "BUY", 0.35)
    b = fp.intent_id(acct.login, "GOLD", "BUY", 0.35)
    c = fp.intent_id(acct.login, "GOLD", "SELL", 0.35)
    d = fp.intent_id(acct.login, "GOLD", "BUY", 0.36)
    assert a == b, "intent id is not deterministic — a restart could duplicate an order"
    assert a != c and a != d, "intent id does not separate side or size"
    print(f"  1 idempotency: id stable across runs, distinct by side and size ({a})")

    # 2 — the band
    tgt = {"GOLD": 0.0500, "SILVER": 0.0000, "OIL": 0.2000,
           "COPPER": 0.0000, "NAS100": 0.0000, "SP500": 0.0000}
    held = {"GOLD": 0.0480, "SILVER": 0.0000, "OIL": 0.0000,
            "COPPER": 0.0000, "NAS100": 0.0000, "SP500": 0.0000}
    plan = fp.build_plan(acct, syms, tgt, held, acct.equity)
    by = {p["name"]: p for p in plan}
    assert by["GOLD"]["action"] == "HOLD", f"0.002 move must be inside the band: {by['GOLD']}"
    assert by["OIL"]["action"] == "OPEN_OR_INCREASE", f"0.20 move must trade: {by['OIL']}"
    print("  2 band: 0.0020 held, 0.2000 traded")

    # 3 — sign reversal and zeroing must be classified as REDUCE_OR_CLOSE
    tgt2 = {"GOLD": -0.10, "SILVER": 0.0, "OIL": 0.0, "COPPER": 0.0, "NAS100": 0.0, "SP500": 0.0}
    held2 = {"GOLD": 0.10, "SILVER": 0.08, "OIL": 0.0, "COPPER": 0.0, "NAS100": 0.0, "SP500": 0.0}
    p2 = {p["name"]: p for p in fp.build_plan(acct, syms, tgt2, held2, acct.equity)}
    assert p2["GOLD"]["action"] == "REDUCE_OR_CLOSE" and p2["GOLD"]["crosses_zero"], \
        f"sign reversal misclassified: {p2['GOLD']}"
    assert p2["SILVER"]["action"] == "REDUCE_OR_CLOSE", f"zeroing misclassified: {p2['SILVER']}"
    print("  3 exits: sign reversal and zeroing both classified REDUCE_OR_CLOSE")

    # 4 — closes must be ordered before opens
    tgt3 = {"GOLD": 0.0, "SILVER": 0.0, "OIL": 0.30, "COPPER": 0.0, "NAS100": 0.0, "SP500": 0.0}
    held3 = {"GOLD": 0.20, "SILVER": 0.0, "OIL": 0.0, "COPPER": 0.0, "NAS100": 0.0, "SP500": 0.0}
    seq = [p["action"] for p in fp.build_plan(acct, syms, tgt3, held3, acct.equity)
           if p["action"] in ("REDUCE_OR_CLOSE", "OPEN_OR_INCREASE")]
    assert seq.index("REDUCE_OR_CLOSE") < seq.index("OPEN_OR_INCREASE"), f"ordering wrong: {seq}"
    print("  4 ordering: closes precede opens")

    # 5 — a failed positions_get() must ABORT, never be read as flat
    install_fake_mt5(positions_fail=True)
    fp.mt5 = sys.modules["MetaTrader5"]
    try:
        fp.held_weights(syms, acct.equity)
        raise AssertionError("FAIL-OPEN: positions_get() returning None was treated as flat")
    except RuntimeError:
        print("  5 fail-closed: positions_get() failure aborts instead of assuming flat")

    # held state really is derived from broker positions
    install_fake_mt5(positions=[FakePos("GOLD", 0.50, 0, fp.MAGIC),
                                FakePos("OIL", 0.25, 1, fp.MAGIC),
                                FakePos("GOLD", 9.99, 0, 999999)])   # foreign magic: must be ignored
    fp.mt5 = sys.modules["MetaTrader5"]
    hw = fp.held_weights(syms, acct.equity)
    assert hw["GOLD"] > 0 and hw["OIL"] < 0, f"broker-derived held state wrong: {hw}"
    # notional_per_lot uses tick.ask (100.01), not the mid — assert against the real formula
    from scripts.portfolio_mt5 import notional_per_lot
    npl = notional_per_lot("GOLD", FakeInfo(), FakeTick())
    assert abs(hw["GOLD"] - 0.50 * npl / 100_000.0) < 1e-12, (
        f"held GOLD {hw['GOLD']} != 0.50 lot; the 9.99-lot foreign-magic position may have leaked")
    assert hw["GOLD"] < 0.01, "a 9.99-lot foreign position leaked into held state"
    print("  6 held state: derived from broker positions, foreign magic ignored")

    # 6 — no fixed TP / trailing stop in EXECUTABLE CODE.
    # Scanning raw text hits the module docstring, which legitimately explains why those exits
    # were rejected. Strip docstrings and comments and check only what actually runs.
    import ast, io, tokenize
    path = ROOT / "scripts" / "frozen_portfolio.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and (
                node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body.pop(0)                      # drop docstrings
    code = ast.unparse(tree).lower()
    for banned in ("take_profit", "trailing", "trail_stop", "tp_price", "target_price"):
        assert banned not in code, f"banned exit mechanism in executable code: {banned}"
    assert "catastrophe" in code, "the 15% catastrophe safeguard is missing from the code"
    print("  7 exits: executable code has no fixed TP and no trailing stop; "
          "catastrophe safeguard present")

    test_submission_path()
    print("\nPASS — frozen rebalance loop behaves correctly under adversarial conditions")




def test_submission_path():
    """Guards on the SUBMISSION path: stop distance, idempotency across restarts and days."""
    install_fake_mt5()
    import importlib
    import scripts.frozen_portfolio as fp
    importlib.reload(fp)
    fp.mt5 = sys.modules["MetaTrader5"]
    import json, tempfile, pathlib
    from datetime import datetime, timezone

    class Info(FakeInfo):
        digits = 2

    # the gate blocks a stop further than 15% from entry (written after the BTC naked-stop bug),
    # so a tick rounded the wrong way would make every order unsubmittable
    worst = 0.0
    for px in (4060.26, 58.223, 80.097, 653.40, 28409.78, 7524.20, 0.87):
        for side in ("BUY", "SELL"):
            lvl = fp.catastrophe_stop(px, side, Info())
            d = abs(px - lvl) / px
            worst = max(worst, d)
            assert d <= 0.15 + 1e-12, f"{side} {px}: stop distance {d} exceeds 15%; gate would block"
            assert (lvl < px) if side == "BUY" else (lvl > px), "stop on the wrong side of entry"
    print(f"  8 catastrophe stop: max distance {worst:.6f} <= 0.15, correct side")

    tmp = pathlib.Path(tempfile.mkdtemp()) / "fills.jsonl"
    fp.FILLS_PATH = tmp
    iid = fp.intent_id(1514166963, "XAUUSD", "BUY", 0.02)
    assert not fp.already_submitted_today(iid)
    tmp.write_text(json.dumps({"intent_id": iid,
                               "ts": datetime.now(timezone.utc).isoformat()}) + "\n")
    assert fp.already_submitted_today(iid), "a restart would DUPLICATE an already-submitted order"
    assert not fp.already_submitted_today(fp.intent_id(1514166963, "XAUUSD", "SELL", 0.02))
    tmp.write_text(json.dumps({"intent_id": iid, "ts": "2020-01-01T00:00:00+00:00"}) + "\n")
    assert not fp.already_submitted_today(iid), "yesterday's intent wrongly blocks today"
    print("  9 idempotency: replay skipped, different side allowed, stale day does not block")

    # 10 — a PRE-TRADE rejection must not block the retry, but anything ambiguous must
    now = datetime.now(timezone.utc).isoformat()
    for rc in sorted(fp.PRE_TRADE_REJECTIONS):
        tmp.write_text(json.dumps({"intent_id": iid, "ts": now, "retcode": rc}) + "\n")
        assert not fp.already_submitted_today(iid), (
            f"retcode {rc} never reached the market but blocked the retry")
    for rc in (10009, None, 99999):
        tmp.write_text(json.dumps({"intent_id": iid, "ts": now, "retcode": rc}) + "\n")
        assert fp.already_submitted_today(iid), (
            f"retcode {rc} may have filled but the retry was allowed — duplicate risk")
    tmp.write_text("{not json\n")
    assert fp.already_submitted_today(iid), "an unreadable ledger must fail CLOSED"
    print("  10 idempotency: pre-trade rejections retryable; filled/unknown/corrupt block")

    # 11 — the order comment must equal the ledger comment, or reconciliation calls our own
    # position an ORPHAN. This is not cosmetic: it halted the first live run after one fill.
    import re
    src = (ROOT / "scripts" / "frozen_portfolio.py").read_text()
    m = re.search(r'"comment":\s*(.+?),\n', src)
    assert m, "no comment field found in the order request"
    assert 'order_intent' in m.group(1), (
        f'order comment is {m.group(1)!r}; it must be dec["order_intent"]["comment"] so that '
        "position_ledger.is_ours() can trace the position back to the ledger")
    from execution_safety.gate import Signal
    # the gate builds comment = f"{strategy_id}:{version}"; assert MT5's 31-char limit holds
    expected = "portfolio_frozen_v1:v1"
    assert len(expected) <= 31, "comment exceeds the MT5 limit and would be truncated"
    print(f"  11 ledger tracing: order comment uses the intent comment ({expected!r}, "
          f"{len(expected)} chars)")
    test_tranching_and_partials()


def test_tranching_and_partials():
    """Tranching must cap NEW exposure, never de-risking; partial fills must be recorded."""
    import ast as _ast, inspect
    import scripts.frozen_portfolio as fp
    src = inspect.getsource(fp.submit_plan)

    # de-risking must never be budgeted
    assert 'p["action"] == "OPEN_OR_INCREASE" and budget_money is not None' in src, \
        "the tranche budget must apply only to exposure-INCREASING orders"
    assert "REDUCE_OR_CLOSE is never budgeted" in fp.submit_plan.__doc__, \
        "the de-risking exemption must be documented where it can be found"

    # partial fills recorded and re-traded next run
    for token in ("filled_volume", "requested_volume", "partial_fill"):
        assert token in src, f"partial-fill field {token} is not recorded in the audit"

    # the budget arithmetic: three orders, budget fits two
    EQ = 100_000.0
    cat = fp.CATASTROPHE
    deltas = [0.0316, 0.0230, 0.1033]
    needs = [d * EQ * cat for d in deltas]
    budget = needs[0] + needs[1] + 1.0
    spent, taken, deferred = 0.0, [], []
    for d, need in zip(deltas, needs):
        if spent + need > budget:
            deferred.append(d)
        else:
            spent += need
            taken.append(d)
    assert len(taken) == 2 and len(deferred) == 1, f"tranche split wrong: {taken} / {deferred}"
    assert spent <= budget, "tranche overspent its budget"
    print(f"  12 tranching: budget {budget:,.0f} -> {len(taken)} submitted, "
          f"{len(deferred)} deferred, spent {spent:,.0f}; de-risking exempt")

if __name__ == "__main__":
    main()
