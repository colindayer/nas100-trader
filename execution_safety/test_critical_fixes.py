"""Regression tests for V-01, V-02, V-04, V-12. Each proves the defect is closed by simulating a
real process restart (constructing fresh objects against the same on-disk state)."""
import sys, os, json, time, tempfile, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from execution_safety import safety_state as ss
from execution_safety.demo_evidence import LimitedDemoEnvelope
from execution_safety.startup_reconciler import reconcile, report

def _tmp(): return os.path.join(tempfile.mkdtemp(), "safety_state.json")
def _pos(symbol="EURUSD", magic=880001, comment="portfolio:funded", sl=1.09, vol=0.1):
    return types.SimpleNamespace(symbol=symbol, magic=magic, comment=comment, sl=sl, volume=vol,
                                 tp=None, ticket=1)

# ---------------- V-01: daily cap survives restart ----------------
def test_v01_restart_after_3_trades_blocks_the_4th():
    p=_tmp()
    e1=LimitedDemoEnvelope(max_trades_per_day=3, state_path=p)
    for i in range(3):
        assert e1.allow(0)[0] is True, f"trade {i+1} should be allowed"
        e1.record_trade(f"OI-{i}")
    assert e1.allow(0) == (False, "DAILY_TRADE_LIMIT")
    e2=LimitedDemoEnvelope(max_trades_per_day=3, state_path=p)      # <-- PROCESS RESTART
    ok, why = e2.allow(0)
    assert ok is False and why == "DAILY_TRADE_LIMIT", f"4th trade after restart: {ok},{why}"
    assert e2.trades_today() == 3

def test_v01_counter_resets_only_on_utc_day_rollover():
    p=_tmp()
    e=LimitedDemoEnvelope(max_trades_per_day=3, state_path=p)
    e.record_trade(); e.record_trade(); e.record_trade()
    assert e.allow(0)[0] is False
    st,_=ss.load(p); st.day="2000-01-01"; ss.save(st,p)             # simulate yesterday
    e2=LimitedDemoEnvelope(max_trades_per_day=3, state_path=p)
    assert e2.allow(0)[0] is True and e2.trades_today()==0

# ---------------- V-02: halt survives restart ----------------
def test_v02_restart_after_halt_remains_halted():
    p=_tmp()
    e1=LimitedDemoEnvelope(state_path=p)
    e1.halt("critical reconciliation failure")
    assert e1.allow(0)[0] is False
    e2=LimitedDemoEnvelope(state_path=p)                            # <-- PROCESS RESTART
    ok, why = e2.allow(0)
    assert ok is False and "HALTED" in why, f"halt did not survive restart: {ok},{why}"

def test_v02_halt_survives_day_rollover():
    p=_tmp()
    LimitedDemoEnvelope(state_path=p).halt("boom")
    st,_=ss.load(p); st.day="2000-01-01"; ss.save(st,p)
    e=LimitedDemoEnvelope(state_path=p)
    assert e.halted is True, "day rollover must NOT clear a halt"

def test_v02_halt_requires_explicit_human_clear():
    p=_tmp()
    LimitedDemoEnvelope(state_path=p).halt("boom")
    try:
        ss.clear_halt("", path=p); assert False, "empty actor must be rejected"
    except ValueError: pass
    ss.clear_halt("human:colindayer", note="investigated", path=p)
    assert LimitedDemoEnvelope(state_path=p).allow(0)[0] is True

# ---------------- corruption fails closed ----------------
def test_corrupt_state_fails_closed():
    p=_tmp(); ss.save(ss.SafetyState(), p)
    open(p,"w").write("{ not json")
    st, notes = ss.load(p)
    assert st.halted is True and "UNREADABLE" in st.halt_reason

def test_checksum_tamper_fails_closed():
    p=_tmp(); ss.save(ss.SafetyState(trades_today=3), p)
    b=json.load(open(p)); b["payload"]["trades_today"]=0            # tamper, keep old digest
    json.dump(b, open(p,"w"))
    st,_=ss.load(p)
    assert st.halted is True and "CHECKSUM" in st.halt_reason

def test_schema_version_mismatch_fails_closed():
    p=_tmp(); ss.save(ss.SafetyState(), p)
    b=json.load(open(p)); b["payload"]["schema_version"]=999
    b["digest"]=ss._digest(b["payload"]); json.dump(b, open(p,"w"))
    st,_=ss.load(p)
    assert st.halted is True and "SCHEMA" in st.halt_reason

# ---------------- V-04: guardian baselines survive restart ----------------
def test_v04_drawdown_baseline_survives_restart():
    p=_tmp()
    ss.load(p, equity=50000)                                        # day start at 50k
    dse, hwm = ss.guardian_baselines(equity=50000, path=p)
    assert dse == 50000 and hwm == 50000
    ss.update_equity(48000, path=p)                                 # account drops
    dse2, hwm2 = ss.guardian_baselines(equity=48000, path=p)        # <-- RESTART at lower equity
    assert dse2 == 50000, f"day_start must NOT follow equity down: {dse2}"
    assert hwm2 == 50000, f"high-water mark must NOT reset: {hwm2}"
    assert (dse2 - 48000)/dse2 == 0.04                              # 4% drawdown is now visible

def test_v04_hwm_ratchets_up_only():
    p=_tmp(); ss.load(p, equity=50000)
    ss.update_equity(52000, path=p); ss.update_equity(49000, path=p)
    _, hwm = ss.guardian_baselines(path=p)
    assert hwm == 52000

# ---------------- V-12: startup reconciliation ----------------
class _Led:
    def __init__(self, known=(), entries=None):
        self._k=set(known); self.entries=entries or {}
    def is_ours(self, magic, comment): return comment in self._k

def test_v12_clean_reconciliation_passes():
    p=_tmp()
    r=reconcile(positions=[_pos()], ledger=_Led(known=["portfolio:funded"]), state_path=p)
    assert r["ok"] is True and r["trading_allowed"] is True

def test_v12_detects_orphan_position_and_halts():
    p=_tmp()
    r=reconcile(positions=[_pos(comment="unknown")], ledger=_Led(known=[]), state_path=p)
    assert any(f["type"]=="ORPHAN_POSITION" for f in r["findings"])
    assert r["trading_allowed"] is False
    assert LimitedDemoEnvelope(state_path=p).halted is True

def test_v12_detects_naked_position():
    p=_tmp()
    r=reconcile(positions=[_pos(sl=0.0)], ledger=_Led(known=["portfolio:funded"]), state_path=p)
    assert any(f["type"]=="NAKED_POSITION" for f in r["findings"])
    assert r["trading_allowed"] is False

def test_v12_detects_foreign_position_without_halting():
    p=_tmp()
    r=reconcile(positions=[_pos(magic=770001, comment="BTC")], ledger=_Led(known=[]), state_path=p)
    assert any(f["type"]=="FOREIGN_POSITION" for f in r["findings"])
    assert r["trading_allowed"] is True          # foreign != ours; report, don't halt

def test_v12_detects_missing_fill():
    p=_tmp()
    e=types.SimpleNamespace(intent_id="OI-1", symbol="EURUSD", comment="portfolio:funded",
                            magic=880001, status="AUTHORIZED", created_at=time.time()-7200)
    r=reconcile(positions=[], ledger=_Led(known=["portfolio:funded"], entries={"OI-1":e}),
                state_path=p, require_broker=False)
    assert any(f["type"]=="MISSING_FILL" for f in r["findings"])

def test_v12_broker_unavailable_blocks_when_required():
    p=_tmp()
    r=reconcile(positions=None, ledger=_Led(), state_path=p, require_broker=True)
    assert r["trading_allowed"] is False
    assert LimitedDemoEnvelope(state_path=p).halted is True

def test_v12_report_renders():
    p=_tmp()
    r=reconcile(positions=[_pos()], ledger=_Led(known=["portfolio:funded"]), state_path=p)
    assert "STARTUP RECONCILIATION" in report(r)

# ---------------- audit trail ----------------
def test_every_transition_is_audited():
    d=tempfile.mkdtemp(); p=os.path.join(d,"s.json"); a=os.path.join(d,"audit.jsonl")
    ss.AUDIT_PATH_ORIG=ss.AUDIT_PATH; ss.AUDIT_PATH=a
    try:
        ss.load(p, equity=50000); ss.record_trade("OI-1", path=p); ss.halt("test", path=p)
        ss.clear_halt("human:test", path=p)
        events=[json.loads(l)["event"] for l in open(a)]
        for want in ("state_initialised","trade_recorded","HALT","HALT_CLEARED"):
            assert want in events, f"{want} not audited: {events}"
    finally:
        ss.AUDIT_PATH=ss.AUDIT_PATH_ORIG

# ---------------- concurrency: two processes cannot overspend the envelope ----------------
def test_two_processes_cannot_overspend_envelope():
    p=_tmp()
    e=LimitedDemoEnvelope(max_trades_per_day=3, state_path=p)
    import threading
    def spend():
        for _ in range(5):
            try:
                e.record_trade(f"OI-{time.time_ns()}")      # atomic claim; refuses past the cap
            except ss.EnvelopeExhausted:
                return
    ts=[threading.Thread(target=spend) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    st,_=ss.load(p)
    assert st.trades_today <= 3, f"envelope overspent under concurrency: {st.trades_today}"

def test_lock_prevents_concurrent_writer():
    p=_tmp(); ss.save(ss.SafetyState(), p)
    lp=ss.acquire(p, timeout=1)
    try:
        try:
            ss.acquire(p, timeout=0.2); assert False, "second writer must be refused"
        except ss.StateLocked: pass
    finally:
        ss.release(lp)
    ss.release(ss.acquire(p, timeout=1))          # lock is reusable after release

def test_record_trade_is_idempotent():
    p=_tmp()
    ss.record_trade("OI-SAME", path=p); ss.record_trade("OI-SAME", path=p)
    st,_=ss.load(p)
    assert st.trades_today == 1, f"duplicate intent double-counted: {st.trades_today}"

# ---------------- bootstrap + backup recovery ----------------
def test_missing_state_documented_safe_bootstrap():
    p=_tmp()
    st, notes = ss.load(p, equity=50000)
    assert os.path.exists(p) and st.halted is False and st.trades_today == 0
    assert st.day_start_equity == 50000 and st.high_water_mark == 50000
    assert any("initialised" in n for n in notes)

def test_backup_recovers_unreadable_primary():
    p=_tmp()
    ss.save(ss.SafetyState(trades_today=2), p)
    ss.save(ss.SafetyState(trades_today=2), p)          # second save creates the .bak
    open(p,"w").write("{ corrupt")
    st, notes = ss.load(p)
    assert st.halted is False and st.trades_today == 2, (st.halted, st.trades_today)
    assert any("BACKUP" in n for n in notes)

# ---------------- reconciliation: remaining detections ----------------
def test_v12_detects_orphan_intent():
    p=_tmp()
    e=types.SimpleNamespace(intent_id="OI-9", symbol="EURUSD", comment="ghost",
                            magic=880001, status="AUTHORIZED", created_at=time.time()-7200)
    r=reconcile(positions=[], ledger=_Led(known=["ghost"], entries={"OI-9":e}),
                state_path=p, require_broker=False)
    assert any(f["type"]=="MISSING_FILL" and f["intent_id"]=="OI-9" for f in r["findings"])

def test_v12_detects_fill_without_ledger_evidence():
    p=_tmp()
    r=reconcile(positions=[_pos(comment="no-ledger-entry")], ledger=_Led(known=[]), state_path=p)
    assert any(f["type"]=="ORPHAN_POSITION" for f in r["findings"])
    assert r["trading_allowed"] is False

def test_v12_reconciliation_failure_blocks_execution_path():
    """A failed reconciliation must halt the persistent state, so the runner's envelope
    refuses regardless of what market intelligence produced."""
    p=_tmp()
    reconcile(positions=[_pos(comment="orphan")], ledger=_Led(known=[]), state_path=p)
    env=LimitedDemoEnvelope(state_path=p)
    ok, why = env.allow(0)
    assert ok is False and "HALTED" in why


if __name__=="__main__":
    fns=[v for k,v in list(globals().items()) if k.startswith("test_")]; p=0
    for fn in fns:
        try: fn(); p+=1; print("PASS", fn.__name__)
        except AssertionError as e: print("FAIL", fn.__name__, e)
        except Exception as e: print("ERR ", fn.__name__, repr(e))
    print(f"\n{p}/{len(fns)} critical-fix regressions proven")

