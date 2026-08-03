"""Adversarial tests for the three-concept account risk model.

    python tests/test_account_risk.py

Each test corresponds to a bug the first live dry-run exposed.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Deal:
    def __init__(self, typ, profit, com=0.0, swap=0.0):
        self.type, self.profit, self.commission, self.swap = typ, profit, com, swap


class Pos:
    def __init__(self, sym, vol, px, sl, profit, magic=880001):
        self.symbol, self.volume, self.price_open = sym, vol, px
        self.sl, self.profit, self.magic = sl, profit, magic


def fake_mt5(positions=(), deals=(), equity=100_000.0, balance=100_000.0, server="FTMO-Demo"):
    m = types.SimpleNamespace()
    m.account_info = lambda: types.SimpleNamespace(login=1514166963, server=server,
                                                   equity=equity, balance=balance)
    m.positions_get = lambda **k: list(positions)
    m.symbol_info = lambda s: types.SimpleNamespace(trade_contract_size=100.0)
    m.symbol_info_tick = lambda s: types.SimpleNamespace(ask=4033.0)
    m.history_deals_get = lambda a, b=None, **k: list(deals)
    sys.modules["MetaTrader5"] = m
    return m


def main():
    from execution_safety import account_risk as ar

    # 1 — a BALANCE deposit must not be counted as realised P&L
    m = fake_mt5(deals=[Deal(2, 100_000.0), Deal(0, -55.84)])
    r = ar.assess(m, 880001, 100_000.0, 0.05)
    assert abs(r.realised_pnl_today - (-55.84)) < 1e-9, (
        f"realised P&L {r.realised_pnl_today} — the 100,000 deposit leaked in")
    print(f"  1 deposits excluded: realised P&L today {r.realised_pnl_today:,.2f}")

    # 2 — limits come from the INITIAL balance, not the drifting current balance
    m = fake_mt5(equity=92_000.0, balance=92_000.0)
    r = ar.assess(m, 880001, 100_000.0, 0.05)
    assert abs(r.daily_loss_limit_money - 5_000.0) < 1e-9, "daily limit drifted with equity"
    assert abs(r.total_loss_limit_money - 10_000.0) < 1e-9, "total limit drifted with equity"
    assert abs(r.total_loss_used_money - 8_000.0) < 1e-9, "total loss used is wrong"
    print(f"  2 limits fixed to initial balance: daily {r.daily_loss_limit_money:,.0f}, "
          f"total {r.total_loss_limit_money:,.0f}, used {r.total_loss_used_money:,.0f}")

    # 3 — a FLAT account must have a POSITIVE budget. Folding the proposal into current stress
    #     made this 0.00 and the engine could never open anything.
    m = fake_mt5()
    r = ar.assess(m, 880001, 100_000.0, 0.05, proposed_gross=0.335,
                  proposed_catastrophe_pct=0.15 * 100 * 0.335)
    assert r.ok, f"a flat account must not be blocked: {r.reasons}"
    assert r.max_additional_catastrophe_money > 4_000, (
        f"budget {r.max_additional_catastrophe_money} — proposal was double-counted")
    print(f"  3 flat account: budget {r.max_additional_catastrophe_money:,.0f} > 0, verdict OK")

    # 4 — an EXISTING book that already breaches headroom must block
    heavy = [Pos("XAUUSD", 2.0, 4000.0, 3400.0, 0.0)] * 5       # huge stress
    m = fake_mt5(positions=heavy)
    r = ar.assess(m, 880001, 100_000.0, 0.05)
    assert not r.ok and "CATASTROPHE_STRESS_EXCEEDS_HEADROOM" in r.reasons, \
        f"an over-exposed book must block: {r.reasons}"
    assert r.max_additional_catastrophe_money == 0.0
    print(f"  4 over-exposed book blocks: stress {r.catastrophe_stress_pct:.1f}% -> {r.reasons}")

    # 5 — unreadable inputs fail CLOSED
    m = fake_mt5()
    m.positions_get = lambda **k: None
    r = ar.assess(m, 880001, 100_000.0, 0.05)
    assert "POSITIONS_UNREADABLE" in r.reasons and not r.ok, "unreadable positions must block"
    m2 = fake_mt5()
    m2.history_deals_get = lambda a, b=None, **k: None
    r2 = ar.assess(m2, 880001, 100_000.0, 0.05)
    assert "DEAL_HISTORY_UNREADABLE" in r2.reasons and not r2.ok, "unreadable deals must block"
    print("  5 fail-closed: unreadable positions or deal history both block")

    # 6 — the three concepts stay distinct and are not conflated
    m = fake_mt5(positions=[Pos("XAUUSD", 0.02, 4062.28, 3452.89, -0.14)])
    r = ar.assess(m, 880001, 100_000.0, 0.05, proposed_gross=0.335)
    assert r.expected_bad_day_money < r.catastrophe_stress_money, \
        "expected bad day should be far smaller than the catastrophe stress"
    assert r.expected_bad_day_money < r.daily_headroom_money, \
        "a 3-sigma day must sit inside the daily headroom"
    print(f"  6 concepts distinct: bad day {r.expected_bad_day_money:,.0f} << "
          f"stress {r.catastrophe_stress_money:,.0f} < headroom {r.daily_headroom_money:,.0f}")

    # 7 — gate magic must be rebound to the trading magic, or every position is an orphan
    src = (ROOT / "scripts" / "frozen_portfolio.py").read_text()
    assert 'dec["order_intent"]["magic_number"] = MAGIC' in src, \
        "the intent must be rebound to MAGIC; gate.py hardcodes 770001 and is_ours() would never match"
    assert '"magic": dec["order_intent"]["magic_number"]' in src, \
        "the order must send the intent's magic so ledger and broker agree by construction"
    print("  7 magic binding: intent and order share MAGIC (gate's 770001 would orphan everything)")

    print("\nPASS — account risk model behaves correctly under adversarial conditions")


if __name__ == "__main__":
    main()
