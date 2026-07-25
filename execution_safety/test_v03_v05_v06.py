"""Regressions for V-03 (contract signing), V-05 (atomic belief store), V-06 (locked ledger)."""
import sys, os, json, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from execution_safety.strategy_contract import StrategyContract, StrategyRegistry, content_hash
from execution_safety.belief_graph_v2 import BeliefGraphV2, Evidence
from execution_safety.position_ledger import PositionLedger

def _dir(): return tempfile.mkdtemp()
def _c(**kw):
    d=dict(strategy_id="s1",strategy_name="S",strategy_family="f",version="v1",code_commit="abc",
           status="PAPER_APPROVED",approved_trial_ids=["TR-1"],permitted_symbols=["EURUSD"],
           maximum_risk_per_trade=0.001,maximum_concurrent_positions=1)
    d.update(kw); return StrategyContract(**d)

# ---------------- V-03 ----------------
def test_v03_signed_contract_authorises():
    p=_dir(); r=StrategyRegistry(path=p); r.save(_c())
    r2=StrategyRegistry(path=p)
    c=r2.get("s1")
    assert c.signature_valid is True and c.may_trade_demo() is True and r2.rejected==[]

def test_v03_unsigned_contract_cannot_authorise():
    p=_dir()
    d=_c().__dict__.copy(); d.pop("signature_valid",None); d["content_hash"]=""
    json.dump(d, open(os.path.join(p,"s1.json"),"w"))
    r=StrategyRegistry(path=p); c=r.get("s1")
    assert c.signature_valid is False and c.may_trade_demo() is False
    assert c.status=="RESEARCH_ONLY", "unsigned must be downgraded, not trusted"
    assert any(x["reason"]=="UNSIGNED" for x in r.rejected)

def test_v03_tampered_status_is_rejected():
    """The exact attack: edit status to LIVE_APPROVED on disk."""
    p=_dir(); r=StrategyRegistry(path=p); r.save(_c(status="RESEARCH_ONLY"))
    f=os.path.join(p,"s1.json"); d=json.load(open(f))
    d["status"]="LIVE_APPROVED"                       # forge the approval, keep the old hash
    json.dump(d, open(f,"w"))
    r2=StrategyRegistry(path=p); c=r2.get("s1")
    assert c.signature_valid is False
    assert c.may_trade_real() is False and c.may_trade_demo() is False
    assert c.status=="RESEARCH_ONLY"
    assert any(x["reason"]=="SIGNATURE_MISMATCH" for x in r2.rejected)

def test_v03_tampered_symbols_rejected():
    p=_dir(); r=StrategyRegistry(path=p); r.save(_c())
    f=os.path.join(p,"s1.json"); d=json.load(open(f))
    d["permitted_symbols"]=["EURUSD","BTCUSD"]        # widen scope
    json.dump(d, open(f,"w"))
    assert StrategyRegistry(path=p).get("s1").may_trade_demo() is False

def test_v03_non_governance_field_does_not_break_signature():
    p=_dir(); r=StrategyRegistry(path=p); r.save(_c(cost_model="3bps"))
    f=os.path.join(p,"s1.json"); d=json.load(open(f))
    d["strategy_name"]="renamed"                      # cosmetic, not in SIGNED_FIELDS
    json.dump(d, open(f,"w"))
    assert StrategyRegistry(path=p).get("s1").signature_valid is True

def test_v03_hmac_mode_when_key_set():
    os.environ["CONTRACT_SIGNING_KEY"]="secret"
    try:
        h1=content_hash({"strategy_id":"s1"})
        os.environ["CONTRACT_SIGNING_KEY"]="other"
        assert content_hash({"strategy_id":"s1"})!=h1
    finally:
        os.environ.pop("CONTRACT_SIGNING_KEY",None)

# ---------------- V-05 ----------------
def test_v05_belief_store_roundtrips():
    p=os.path.join(_dir(),"b.json")
    g=BeliefGraphV2(path=p); g.add("s1", Evidence("e1","WalkForward",True,2.0))
    g2=BeliefGraphV2(path=p)
    assert g2.corrupt is False and len(g2.get("s1").evidence)==1

def test_v05_corrupt_store_flagged_not_silently_empty():
    p=os.path.join(_dir(),"b.json")
    g=BeliefGraphV2(path=p); g.add("s1", Evidence("e1","WalkForward",True,2.0))
    open(p,"w").write("{ corrupt")
    os.remove(p+".bak") if os.path.exists(p+".bak") else None
    g2=BeliefGraphV2(path=p)
    assert g2.corrupt is True, "corruption must be FLAGGED, not read as an empty graph"

def test_v05_digest_tamper_detected():
    p=os.path.join(_dir(),"b.json")
    g=BeliefGraphV2(path=p); g.add("s1", Evidence("e1","WalkForward",True,2.0))
    b=json.load(open(p)); b["payload"]["s1"]["research_prior"]=0.99   # tamper, keep digest
    json.dump(b, open(p,"w"))
    if os.path.exists(p+".bak"): os.remove(p+".bak")
    assert BeliefGraphV2(path=p).corrupt is True

def test_v05_backup_recovers_belief_store():
    p=os.path.join(_dir(),"b.json")
    g=BeliefGraphV2(path=p); g.add("s1", Evidence("e1","WalkForward",True,2.0))
    g.add("s1", Evidence("e2","Bootstrap",True,1.0))       # second save creates .bak
    open(p,"w").write("{ corrupt")
    g2=BeliefGraphV2(path=p)
    assert g2.corrupt is False and len(g2.get("s1").evidence)>=1

def test_v05_atomic_write_leaves_no_tmp():
    p=os.path.join(_dir(),"b.json")
    g=BeliefGraphV2(path=p); g.add("s1", Evidence("e1","WalkForward",True,2.0))
    leftovers=[f for f in os.listdir(os.path.dirname(p)) if f.startswith(".belief_")]
    assert leftovers==[], f"temp files left behind: {leftovers}"

# ---------------- V-06 ----------------
def _intent(i): return dict(intent_id=f"OI-{i}",strategy_id="s1",strategy_version="v1",
                            symbol="EURUSD",magic_number=880001,comment="c",created_at=time.time())

def test_v06_torn_line_does_not_raise_in_order_path():
    p=os.path.join(_dir(),"led.jsonl")
    led=PositionLedger(path=p); led.record_intent(_intent(1),["TR-1"],"D1")
    with open(p,"a") as f: f.write('{"intent_id": "torn", "bad\n')   # torn write
    led2=PositionLedger(path=p)                                       # must NOT raise
    assert len(led2.entries)==1 and len(led2.malformed)==1

def test_v06_concurrent_appends_are_not_interleaved():
    p=os.path.join(_dir(),"led.jsonl")
    import threading
    def w(n):
        l=PositionLedger(path=p)
        for i in range(10): l.record_intent(_intent(f"{n}-{i}"),["TR"],"D")
    ts=[threading.Thread(target=w,args=(n,)) for n in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    led=PositionLedger(path=p)
    assert led.malformed==[], f"torn lines under concurrency: {led.malformed}"
    assert len(led.entries)==40

def test_v06_blank_lines_ignored():
    p=os.path.join(_dir(),"led.jsonl")
    led=PositionLedger(path=p); led.record_intent(_intent(1),["TR"],"D")
    with open(p,"a") as f: f.write("\n\n")
    assert PositionLedger(path=p).malformed==[]

if __name__=="__main__":
    fns=[v for k,v in list(globals().items()) if k.startswith("test_")]; p=0
    for fn in fns:
        try: fn(); p+=1; print("PASS", fn.__name__)
        except AssertionError as e: print("FAIL", fn.__name__, e)
        except Exception as e: print("ERR ", fn.__name__, repr(e))
    print(f"\n{p}/{len(fns)} V-03/V-05/V-06 regressions proven")
