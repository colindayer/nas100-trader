"""PHASE 601 recovery-stage tests. Run: python -m execution_safety.test_recovery
Proves Stages 5,7,8,10,11 fail closed. No orders placed."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from execution_safety.strategy_contract import StrategyContract
from execution_safety.strategy_registry_shim import Reg
from execution_safety.gate import Signal, authorize
from execution_safety.broker_reconciliation import BrokerPosition, reconcile, protective_stop_monitor
from execution_safety.position_ledger import PositionLedger, LedgerEntry, classify_broker_positions
from execution_safety import shadow


# ---- Stage 7: broker reconciliation ----
def test_missing_broker_stop_is_critical():
    intent = dict(calculated_volume=0.1, magic_number=770001, comment="s:v1", stop_loss=1.09)
    pos = BrokerPosition("EURUSD", 0.1, sl=0.0, tp=None, magic=770001, comment="s:v1")
    r = reconcile(intent, pos)
    assert r["state"] == "CRITICAL" and r["block_new_entries"] and "MISSING_BROKER_STOP" in r["critical"]

def test_naked_position_blocks_new_entries():
    ps = [BrokerPosition("BTCUSD", 0.3, sl=0.0, tp=None, magic=770001, comment="BTC")]
    r = protective_stop_monitor(ps, 770001)
    assert r["block_new_entries"] and r["alert"]

# ---- Stage 8: orphan detection ----
def test_orphan_position_blocks_all():
    led = PositionLedger(path="/tmp/_ledger_test.jsonl"); led.entries = {}
    import types
    foreign = types.SimpleNamespace(symbol="BTCUSD", magic=999999, comment="ScalperEA")
    r = classify_broker_positions([foreign], led, our_magic=770001)
    assert r["block_all_orders"] and r["orphans"]

def test_known_position_not_orphan():
    led = PositionLedger(path="/tmp/_ledger_test2.jsonl"); led.entries = {}
    intent = dict(intent_id="OI1", strategy_id="trend_ema", strategy_version="v1", symbol="EURUSD",
                  magic_number=770001, comment="trend_ema:v1", created_at=time.time())
    led.record_intent(intent, ["TR-1"], "D1")
    import types
    ours = types.SimpleNamespace(symbol="EURUSD", magic=770001, comment="trend_ema:v1")
    r = classify_broker_positions([ours], led, our_magic=770001)
    assert not r["block_all_orders"]

# ---- Stage 11: shadow never places ----
def test_shadow_never_places_even_on_allow():
    c = StrategyContract(strategy_id="trend_ema", strategy_name="t", strategy_family="trend",
                         version="v1", code_commit="x", status="PAPER_APPROVED",
                         approved_trial_ids=["TR-1"], permitted_symbols=["EURUSD"],
                         maximum_risk_per_trade=0.001, maximum_concurrent_positions=1)
    c.sign(); c.signature_valid = c.verify()      # V-03: signed contracts only
    s = Signal("s1", "trend_ema", "v1", "EURUSD", 1, 1.10, 1.095, 1.11)
    d = shadow.shadow_step(s, registry=Reg([c]), inference=lambda x: "ALLOW_PAPER", guardian_ok=True,
                           equity=50000, account_is_demo=True, open_positions=[], log="/tmp/_shadow.jsonl")
    assert d["decision"] == "ALLOW_PAPER" and d["placed_order"] is False and d["would_send"] is not None

# ---- Stage 10: parity replay blocks the real BTC trades ----
def test_parity_blocks_the_btc_trades():
    btc = [dict(ticket=346174109, symbol="BTCUSD", entry=65621.47, sl=52485.18, direction=1),
           dict(ticket=344259068, symbol="BTCUSD", entry=64836.80, sl=52964.24, direction=1)]
    r = shadow.parity_replay(btc, registry=Reg([]), inference=lambda x: "ALLOW_PAPER", equity=50000)
    assert r["would_block"] == 2, r          # both real BTC trades blocked by the rewired gate

if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    p = 0
    for fn in fns:
        try: fn(); p += 1; print("PASS", fn.__name__)
        except AssertionError as e: print("FAIL", fn.__name__, e)
        except Exception as e: print("ERR ", fn.__name__, repr(e))
    print(f"\n{p}/{len(fns)} recovery-stage guarantees proven")

# ---- PHASE 601 gap closure: belief + guardian are REAL and fail closed ----
def test_belief_reader_fails_closed_without_snapshot():
    from execution_safety.belief_reader import decide
    d,det=decide("H_anything", path="/tmp/_no_such_belief.json")
    assert d=="RESEARCH_ONLY" and det["reason"]=="NO_BELIEF_SNAPSHOT"

def test_belief_reader_blocks_below_threshold():
    import json, tempfile, os
    p=os.path.join(tempfile.mkdtemp(),"b.json")
    json.dump({"H":{"prior":0.25,"evidence":[{"supports":True,"weight":0.5}]}},open(p,"w"))
    from execution_safety.belief_reader import decide
    d,det=decide("H", threshold=0.60, path=p)
    assert d=="BLOCK" and det["reason"]=="POSTERIOR_BELOW_THRESHOLD"

def test_belief_reader_allows_above_threshold():
    import json, tempfile, os
    p=os.path.join(tempfile.mkdtemp(),"b.json")
    json.dump({"H":{"prior":0.25,"evidence":[{"supports":True,"weight":3.0}]}},open(p,"w"))
    from execution_safety.belief_reader import decide
    d,_=decide("H", threshold=0.60, path=p)
    assert d=="ALLOW_PAPER"

def test_guardian_bridge_fails_closed_without_mt5():
    from execution_safety.guardian_bridge import guardian_ok
    ok,det=guardian_ok()
    assert ok is False and "reason" in det      # no MT5 here -> must NOT allow
