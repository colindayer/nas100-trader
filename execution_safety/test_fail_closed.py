"""PHASE 601 fail-closed proof. Run: python execution_safety/test_fail_closed.py
Proves unsupported trading is impossible: every gate blocks, and only a fully-approved chain passes.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy_contract import StrategyContract, StrategyRegistry
from gate import Signal, authorize


class Reg(StrategyRegistry):
    def __init__(self, contracts): self.contracts = {c.strategy_id: c for c in contracts}


def approved_contract(**kw):
    d = dict(strategy_id="trend_ema", strategy_name="Trend EMA", strategy_family="trend",
             version="v1", code_commit="abc123", status="PAPER_APPROVED",
             approved_trial_ids=["TR-1"], permitted_symbols=["EURUSD"],
             maximum_risk_per_trade=0.001, maximum_concurrent_positions=1, pyramiding_allowed=False)
    d.update(kw)
    c = StrategyContract(**d)
    c.sign(); c.signature_valid = c.verify()      # V-03: contracts must be signed to authorise
    return c


def sig(**kw):
    d = dict(signal_id="s1", strategy_id="trend_ema", strategy_version="v1",
             symbol="EURUSD", direction=1, entry=1.10, stop_loss=1.095, take_profit=1.11)
    d.update(kw); return Signal(**d)


ALLOW = lambda s: "ALLOW_PAPER"
BASE = dict(inference=ALLOW, guardian_ok=True, equity=50000, account_is_demo=True, open_positions=[])


def run(name, contract, signal, **over):
    kw = {**BASE, **over}
    reg = Reg([contract]) if contract else Reg([])
    return authorize(signal, registry=reg, **kw)


def test_no_contract_blocks():
    d = run("x", None, sig())
    assert d["decision"] == "BLOCK" and "NO_CONTRACT" in d["reason_codes"]

def test_not_paper_approved_blocks():
    d = run("x", approved_contract(status="RESEARCH_ONLY"), sig())
    assert d["decision"] == "BLOCK" and "NOT_PAPER_APPROVED" in d["reason_codes"]

def test_version_mismatch_blocks():
    d = run("x", approved_contract(), sig(strategy_version="v2"))
    assert "VERSION_MISMATCH" in d["reason_codes"]

def test_no_trial_blocks():
    d = run("x", approved_contract(approved_trial_ids=[]), sig())
    assert "NO_APPROVED_TRIAL" in d["reason_codes"] and "approved_trial_ids" in d["missing_evidence"]

def test_missing_stop_blocks():
    d = run("x", approved_contract(), sig(stop_loss=0))
    assert "MISSING_STOP" in d["reason_codes"]

def test_implausible_stop_blocks():
    # the BTC bug: 20% stop -> must be rejected
    d = run("x", approved_contract(), sig(entry=65000, stop_loss=52000))
    assert "STOP_DISTANCE_IMPLAUSIBLE" in d["reason_codes"]

def test_symbol_not_permitted_blocks():
    d = run("x", approved_contract(), sig(symbol="BTCUSD"))
    assert "SYMBOL_NOT_PERMITTED" in d["reason_codes"]

def test_pyramiding_blocked():
    d = run("x", approved_contract(), sig(), open_positions=[{"symbol": "EURUSD"}])
    assert "PYRAMIDING_BLOCKED" in d["reason_codes"]

def test_guardian_veto_cannot_be_overridden():
    d = run("x", approved_contract(), sig(), guardian_ok=False)
    assert d["decision"] == "BLOCK" and "GUARDIAN_VETO" in d["reason_codes"]

def test_inference_block_cannot_be_averaged_away():
    d = run("x", approved_contract(), sig(), inference=lambda s: "BLOCK")
    assert d["decision"] == "BLOCK" and "INFERENCE_BLOCK" in d["reason_codes"]

def test_real_account_needs_live_approved():
    d = run("x", approved_contract(status="PAPER_APPROVED"), sig(), account_is_demo=False)
    assert "NOT_LIVE_APPROVED" in d["reason_codes"]   # PAPER_APPROVED may NOT trade real

def test_rejected_creates_no_intent():
    d = run("x", None, sig())
    assert "order_intent" not in d       # a blocked decision never produces an intent

def test_end_to_end_pass_creates_shadow_intent():
    d = run("x", approved_contract(), sig())
    assert d["decision"] == "ALLOW_PAPER", d["reason_codes"]
    assert d["order_intent"]["calculated_volume"] > 0
    assert d["order_intent"]["stop_loss"] == 1.095
    assert d["shadow"] is True           # shadow mode: intent exists, executor places nothing

def test_signal_has_no_broker_access():
    # structural: authorize() returns a plain dict; nothing here can submit an order.
    import gate, inspect
    src = inspect.getsource(gate)
    assert "order_send" not in src and "place_order" not in src, "gate must not touch a broker"


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    p = 0
    for fn in fns:
        try: fn(); p += 1; print("PASS", fn.__name__)
        except AssertionError as e: print("FAIL", fn.__name__, e)
    print(f"\n{p}/{len(fns)} fail-closed guarantees proven")
