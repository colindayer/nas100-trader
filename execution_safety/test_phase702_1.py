"""PHASE 702.1 regression tests: --demo-limited cannot exceed caps, cannot pyramid, cannot run
below LIMITED_DEMO_APPROVED, and cannot bypass the execution gate."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from execution_safety.belief_graph_v2 import BeliefGraphV2, Evidence
from execution_safety.promotion_pipeline_v2 import evaluate, REQUIREMENTS
from execution_safety.demo_evidence import LimitedDemoEnvelope, record
import tempfile
def _sp():  # isolated safety-state path per test (state is now PERSISTENT)
    return os.path.join(tempfile.mkdtemp(), 'safety_state.json')
from execution_safety.operational_belief import TradeExecutionRecord
from execution_safety.execution_guard import consume_or_block, ExecutionBlocked, armed

def _g(): return BeliefGraphV2(path=os.path.join(tempfile.mkdtemp(), "b.json"))

def _demo_ready(g, sid="S"):
    g.add(sid, Evidence("wf","WalkForward",True,2.2,"walk-forward"))
    g.add(sid, Evidence("sh","Shadow",True,0.6,"shadow clean"))
    return g

def _rec(i, **kw):
    d = dict(trade_id=f"t{i}", symbol="EURUSD", expected_entry=1.10, actual_entry=1.1001,
             expected_spread=8e-5, actual_spread=9e-5, expected_slippage=1e-4, actual_slippage=5e-5,
             stop_verified=True, exit_verified=True, reconciliation_passed=True,
             ledger_recorded=True, no_duplicate=True, symbol_mapped=True, volume_correct=True,
             guardian_approved=True, broker_ack=True, execution_latency_ms=120, broker_retcode=10009)
    d.update(kw); return TradeExecutionRecord(**d)

# 1. cannot exceed the daily trade cap
def test_cannot_exceed_daily_trade_cap():
    e = LimitedDemoEnvelope(max_positions=1, max_trades_per_day=3, state_path=_sp())
    for _ in range(3):
        assert e.allow(0)[0] is True; e.record_trade()
    ok, why = e.allow(0)
    assert ok is False and why == "DAILY_TRADE_LIMIT"

# 2. cannot pyramid / exceed concurrent-position cap
def test_cannot_pyramid_beyond_envelope():
    e = LimitedDemoEnvelope(max_positions=1, state_path=_sp())
    assert e.allow(0)[0] is True
    ok, why = e.allow(1)                      # one already open
    assert ok is False and why == "MAX_POSITIONS"

# 3. risk cap comes from the promotion state and is 0.1% in LIMITED_DEMO
def test_risk_cap_is_enforced_by_state():
    g = _demo_ready(_g())
    st = evaluate("S", g)
    assert st["state"] == "LIMITED_DEMO_APPROVED"
    assert st["risk_cap_pct"] == 0.001 and st["position_cap"] == 1
    e = LimitedDemoEnvelope(max_positions=st["position_cap"], risk_pct=st["risk_cap_pct"], state_path=_sp())
    assert e.risk_pct == 0.001

# 4. cannot execute below LIMITED_DEMO_APPROVED
def test_cannot_execute_below_limited_demo():
    g = _g()                                   # no evidence at all
    st = evaluate("S", g)
    assert st["state"] == "RESEARCH_ONLY"
    assert st["may_trade_demo"] is False and st["position_cap"] == 0

def test_shadow_approved_still_cannot_trade_demo():
    g = _g(); g.add("S", Evidence("bt","Backtest",True,1.2))
    st = evaluate("S", g)
    assert st["state"] == "SHADOW_APPROVED" and st["may_trade_demo"] is False

# 5. cannot bypass the execution gate/guard
def test_cannot_submit_without_arming_the_guard():
    try: consume_or_block("demo-limited"); assert False, "must block"
    except ExecutionBlocked: pass

def test_arming_is_single_use_so_one_decision_is_one_order():
    with armed("D-1"):
        assert consume_or_block("x") == "D-1"
        try: consume_or_block("x"); assert False, "second submit must block"
        except ExecutionBlocked: pass

# 6. critical failure halts immediately and is recorded as evidence against
def test_critical_reconciliation_failure_halts():
    g = _demo_ready(_g()); env = LimitedDemoEnvelope(state_path=_sp())
    out = record(_rec(1, reconciliation_passed=False), "S", g, env)
    assert "reconciliation_passed" in out["critical_failures"]
    assert env.halted is True and env.allow(0)[0] is False

def test_missing_broker_stop_is_critical():
    g = _demo_ready(_g()); env = LimitedDemoEnvelope(state_path=_sp())
    out = record(_rec(2, stop_verified=False), "S", g, env)
    assert "stop_verified" in out["critical_failures"] and env.halted is True

# 7. demo evidence updates operational belief only (capped research influence)
def test_demo_updates_operational_not_research():
    g = _demo_ready(_g())
    r0 = g.get("S").research_belief(); o0 = g.get("S").operational_belief()
    for i in range(40): record(_rec(i), "S", g, None)
    r1 = g.get("S").research_belief(); o1 = g.get("S").operational_belief()
    assert o1 > o0 + 0.4, (o0, o1)
    assert (r1 - r0) <= 0.10, (r0, r1)        # capped by MAX_EXEC_RESEARCH_LOGODDS

# 8. live bar untouched
def test_live_research_bar_unchanged():
    assert REQUIREMENTS["LIVE_APPROVED"]["research_min"] == 0.60

if __name__ == "__main__":
    fns=[v for k,v in list(globals().items()) if k.startswith("test_")]; p=0
    for fn in fns:
        try: fn(); p+=1; print("PASS",fn.__name__)
        except AssertionError as e: print("FAIL",fn.__name__,e)
        except Exception as e: print("ERR ",fn.__name__,repr(e))
    print(f"\n{p}/{len(fns)} PHASE 702.1 guarantees proven")
