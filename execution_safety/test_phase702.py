"""PHASE 702 tests: every promotion state, every belief transition, and the no-leak guarantee."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from execution_safety.belief_graph_v2 import BeliefGraphV2, Evidence, EVIDENCE_CLASSES
from execution_safety.promotion_pipeline_v2 import evaluate, REQUIREMENTS, STATES
from execution_safety.operational_belief import TradeExecutionRecord, to_evidence
from execution_safety.demo_evidence import record, LimitedDemoEnvelope

def _g():
    return BeliefGraphV2(path=os.path.join(tempfile.mkdtemp(), "b.json"))

def _good_trade(i):
    return TradeExecutionRecord(trade_id=f"t{i}", symbol="EURUSD", expected_entry=1.10,
        actual_entry=1.1001, expected_spread=0.00008, actual_spread=0.00009,
        expected_slippage=0.0001, actual_slippage=0.00005, stop_verified=True, exit_verified=True,
        reconciliation_passed=True, ledger_recorded=True, no_duplicate=True, symbol_mapped=True,
        volume_correct=True, guardian_approved=True, broker_ack=True,
        execution_latency_ms=120, broker_retcode=10009)

# ---- separation guarantee ----
def test_demo_execution_cannot_inflate_research_belief_materially():
    g=_g()
    r0=g.get("S").research_belief()
    for i in range(50): g.add("S", to_evidence(_good_trade(i)))
    r1=g.get("S").research_belief(); o1=g.get("S").operational_belief()
    assert o1 > 0.9, o1                      # operational rises a lot
    assert (r1-r0) < 0.45, (r0,r1)           # research only nudges (factor 0.10)

def test_research_evidence_cannot_move_operational_belief():
    g=_g(); o0=g.get("S").operational_belief()
    g.add("S", Evidence("wf1","WalkForward",True,3.0,"strong walk-forward"))
    assert g.get("S").operational_belief()==o0
    assert g.get("S").research_belief() > 0.7

def test_unknown_evidence_class_rejected():
    g=_g()
    try: g.add("S", Evidence("x","Vibes",True,1.0)); assert False
    except ValueError: pass

# ---- every promotion state ----
def test_state_research_only_by_default():
    assert evaluate("NEW", _g())["state"]=="RESEARCH_ONLY"

def test_state_shadow_approved():
    g=_g(); g.add("S", Evidence("bt","Backtest",True,1.2))
    r=evaluate("S",g); assert r["state"]=="SHADOW_APPROVED", r

def test_state_limited_demo_approved_breaks_circularity():
    """The real case: research 0.5748-ish + shadow evidence -> demo allowed, WITHOUT lowering live bar."""
    g=_g()
    g.add("S", Evidence("wf","WalkForward",True,2.2,"Sharpe 0.62 active period"))
    g.add("S", Evidence("audit","Bootstrap",False,0.8,"pass-rate overstated"))
    g.add("S", Evidence("sh1","Shadow",True,0.6,"shadow run clean"))
    r=evaluate("S",g)
    assert r["state"]=="LIMITED_DEMO_APPROVED", r
    assert r["may_trade_demo"] is True and r["may_trade_real"] is False
    assert r["position_cap"]==1 and r["risk_cap_pct"]==0.001

def test_state_full_demo_requires_ops_and_30_trades():
    g=_g()
    g.add("S", Evidence("wf","WalkForward",True,2.4)); g.add("S", Evidence("sh","Shadow",True,0.6))
    r=evaluate("S",g); assert r["state"]=="LIMITED_DEMO_APPROVED"
    for i in range(30): g.add("S", to_evidence(_good_trade(i)))
    r=evaluate("S",g); assert r["state"]=="FULL_DEMO_APPROVED", r
    assert r["position_cap"]==3

def test_state_live_requires_unchanged_060_research_bar():
    assert REQUIREMENTS["LIVE_APPROVED"]["research_min"]==0.60      # must never be lowered
    g=_g()
    g.add("S", Evidence("wf","WalkForward",True,1.0))               # research ~0.5 only
    g.add("S", Evidence("sh","Shadow",True,0.6))
    for i in range(120): g.add("S", to_evidence(_good_trade(i)))    # perfect execution
    r=evaluate("S",g)
    assert r["state"]!="LIVE_APPROVED"                              # ops alone cannot buy LIVE
    assert any("research_belief" in f for f in r["blocking"].get("LIVE_APPROVED",[])), r["blocking"]

def test_live_reachable_only_with_both():
    g=_g()
    g.add("S", Evidence("wf","WalkForward",True,3.0)); g.add("S", Evidence("bs","Bootstrap",True,1.5))
    g.add("S", Evidence("sh","Shadow",True,0.6))
    for i in range(120): g.add("S", to_evidence(_good_trade(i)))
    r=evaluate("S",g); assert r["state"]=="LIVE_APPROVED", r

# ---- defects block promotion ----
def test_critical_defect_blocks_and_halts():
    g=_g(); env=LimitedDemoEnvelope()
    g.add("S", Evidence("wf","WalkForward",True,2.4)); g.add("S", Evidence("sh","Shadow",True,0.6))
    bad=_good_trade(99); bad.stop_verified=False          # naked position = critical
    out=record(bad, "S", g, env)
    assert "stop_verified" in out["critical_failures"]
    assert env.halted is True
    assert out["promotion"]["outstanding_defects"], out["promotion"]

def test_envelope_limits():
    e=LimitedDemoEnvelope(max_positions=1, max_trades_per_day=3)
    assert e.allow(0)[0] is True
    assert e.allow(1)[0] is False                        # position cap
    e.record_trade(); e.record_trade(); e.record_trade()
    assert e.allow(0)[0] is False                        # daily cap
    e2=LimitedDemoEnvelope(); e2.halt("boom"); assert e2.allow(0)[0] is False

if __name__=="__main__":
    fns=[v for k,v in list(globals().items()) if k.startswith("test_")]; p=0
    for fn in fns:
        try: fn(); p+=1; print("PASS",fn.__name__)
        except AssertionError as e: print("FAIL",fn.__name__,e)
        except Exception as e: print("ERR ",fn.__name__,repr(e))
    print(f"\n{p}/{len(fns)} PHASE 702 guarantees proven")
