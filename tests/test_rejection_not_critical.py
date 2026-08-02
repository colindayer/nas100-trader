"""A broker rejection must not halt the system, and must not move OperationalBelief.

Regression for the 2026-08-02 FundedNext incident: retcode 10026
(TRADE_RETCODE_SERVER_DISABLES_AT) was scored as two critical execution failures
(stop_verified, reconciliation_passed), which halted the limited-demo campaign and wrote
weight-1.4 evidence AGAINST the machine for a failure that never occurred.

The fix must NOT weaken anything: an order we cannot confirm stays critical.

    python tests/test_rejection_not_critical.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from execution_safety.operational_belief import TradeExecutionRecord, to_evidence


def rec(**kw):
    base = dict(trade_id="t1", symbol="SP500", ledger_recorded=True, no_duplicate=True,
                symbol_mapped=True, guardian_approved=True, broker_ack=False,
                stop_verified=False, reconciliation_passed=False, volume_correct=False,
                broker_retcode=10026)
    base.update(kw)
    return TradeExecutionRecord(**base)


def main():
    # 1. rejection WITH positive proof of no position -> no critical failures
    r = rec(order_rejected_no_position=True)
    assert r.critical_failures() == [], f"rejection must not be critical, got {r.critical_failures()}"

    # 2. the SAME record without that proof -> still critical. Fail-closed preserved.
    r2 = rec(order_rejected_no_position=False)
    assert "stop_verified" in r2.critical_failures(), "unconfirmed order must stay critical"
    assert "reconciliation_passed" in r2.critical_failures()

    # 3. a REAL defect is still critical even when the rejection flag is set: a position that
    #    exists with no stop must never be excused. ledger_recorded is not a position check.
    r3 = rec(order_rejected_no_position=True, ledger_recorded=False)
    assert "ledger_recorded" in r3.critical_failures(), "non-position criticals must survive"

    # 4. a genuine filled-but-unstopped trade is untouched by any of this
    r4 = rec(broker_ack=True, broker_retcode=10009, volume_correct=True,
             reconciliation_passed=True, stop_verified=False,
             order_rejected_no_position=False)
    assert "stop_verified" in r4.critical_failures(), "a live position without a stop is CRITICAL"

    # 5. evidence weight: the rejection is not counted as a sample by demo_evidence.record(),
    #    but to_evidence itself must not silently mark it as SUPPORTING.
    ev = to_evidence(rec(order_rejected_no_position=True))
    assert ev.supports is False, "a rejection must never read as evidence FOR the machine"

    print("PASS — rejection is not a critical failure; unconfirmed orders and real "
          "unstopped positions still are")


if __name__ == "__main__":
    main()
