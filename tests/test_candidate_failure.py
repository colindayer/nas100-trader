"""TASK-0007 -- a funded candidate that raises must be RECORDED, never silently lost.

On 2026-08-17/18 six funded candidates disappeared between CIO allocation and the broker.
Zero orders, zero events, and the controller log ended mid-cycle because stderr was discarded.
These tests drive the real main() with a fake MetaTrader5 module and prove the failure is now
contained, named by stage, and provably never reaches order_send or the ledger.
"""
import sys, os, io, json, types, tempfile, shutil, pathlib, contextlib
sys.path.insert(0, ".")
import pandas as pd

FAILED = []
def ck(n, c, d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}" + ("" if c else f"   <- {d}"))
    if not c: FAILED.append(n)

# ---- guardian.env is the real binding; the fake account must match it or the demo gate halts
GE = pathlib.Path("config/guardian.env").read_text(encoding="utf-8")
LOGIN = int([l for l in GE.splitlines() if l.startswith("ACCOUNT_LOGIN")][0].split("=")[1])
SERVER = [l for l in GE.splitlines() if l.startswith("ACCOUNT_SERVER_CONTAINS")][0].split("=")[1].strip()

import time as _time
OFF_H = 3                                   # plausible broker offset, inside EXPECTED_OFFSETS_H
def NOW(): return _time.time()
def _rates(n, tf_sec, start_price=4000.0, base=None):
    import numpy as np
    base = base if base is not None else NOW() + OFF_H*3600
    return np.array([(base - (n-i)*tf_sec, start_price, start_price+2, start_price-2,
                      start_price+0.5, 100, 2, 0) for i in range(n)],
        dtype=[('time','i8'),('open','f8'),('high','f8'),('low','f8'),
               ('close','f8'),('tick_volume','i8'),('spread','i4'),('real_volume','i8')])

class FakeMT5:
    TIMEFRAME_D1=16408; TIMEFRAME_H4=16388; TIMEFRAME_H1=16385
    TIMEFRAME_M15=15; TIMEFRAME_M5=5; TIMEFRAME_M1=1
    TRADE_ACTION_DEAL=1; TRADE_RETCODE_DONE=10009
    ORDER_TYPE_BUY=0; ORDER_TYPE_SELL=1; ORDER_TIME_GTC=0; ORDER_FILLING_IOC=1
    def __init__(s): s.orders_sent=[]; s.t=NOW()
    def initialize(s,*a,**k): return True
    def shutdown(s): pass
    def last_error(s): return (0,"ok")
    def account_info(s): return types.SimpleNamespace(login=LOGIN, server=f"{SERVER}-Demo",
        trade_mode=0, equity=100000.0, balance=100000.0, currency="USD")
    def terminal_info(s): return types.SimpleNamespace(trade_allowed=True, connected=True)
    def symbol_select(s,sym,on=True): return True
    def symbol_info_tick(s,sym):
        # broker-stamped, ADVANCING, and current -- otherwise the clock can never go FEED_FRESH
        return types.SimpleNamespace(time=int(s.t + OFF_H*3600), bid=4000.0, ask=4000.5)
    def symbol_info(s,sym): return types.SimpleNamespace(volume_min=0.01, volume_step=0.01,
        volume_max=100.0, trade_tick_value=1.0, trade_tick_size=0.01, trade_contract_size=100.0)
    def copy_rates_from_pos(s,sym,tf,start,count):
        sec={16408:86400,16388:14400,16385:3600,15:900,5:300,1:60}.get(tf,60)
        return _rates(count, sec, base=s.t + OFF_H*3600)
    def positions_get(s,**k): return []
    def orders_get(s,**k): return []
    def history_deals_get(s,*a,**k): return []
    def order_send(s,req): s.orders_sent.append(req); return types.SimpleNamespace(
        retcode=10009, price=4000.5, order=12345, deal=12345, volume=req["volume"])

class RaisingBot:
    """A bot that always produces a candidate. The exception is injected downstream."""
    strategy_id="BOT_TEST_probe"; strategy_version="t1"; symbol="XAUUSD"
    playbook="SWEEP"; shadow=False; risk_override=0.0005; stage="DEMO_CANDIDATE"
    prior_expectancy_R=0.0; prior_n=10; avoids=set(); EXIT_H=23; EXIT_M=59
    no_signal_reason=""
    def generate_signal(self, ctx):
        from bot_base import Signal
        e=ctx["ask"]
        return Signal(self.strategy_id, self.strategy_version, ctx["now_london"].isoformat(),
                      self.symbol, 1, "market", e, e-20.0, e+40.0, 600,
                      ["probe", "level=4000.0"], {"sl_dist":20.0})

def run_cycle(inject_at=None, exc=None, live=True, heal_st=False):
    """Drive the REAL main() with a fake broker. inject_at monkeypatches one stage to raise."""
    d=tempfile.mkdtemp(prefix="t0007-")
    fake=FakeMT5()
    sys.modules["MetaTrader5"]=fake
    for m in ("challenge_controller","market_state","desk","desk_events","trading_brain",
              "macro_context","shadows","bot_base"):
        sys.modules.pop(m, None)
    import challenge_controller as CC, market_state as MS, desk_events as EV
    import trading_brain as TB
    root=pathlib.Path(d)
    CC.DATA=root/"challenge"; CC.LOGS=root/"logs"; CC.TRADES=CC.DATA/"trades.jsonl"
    CC.STATE=CC.DATA/"controller_state.json"; CC.OPEN_STATE=CC.DATA/"open_positions.json"
    CC._CYCLE_MARK=CC.LOGS/".last_cycle"
    MS.CLOCK_STATE_PATH=root/"logs"/"clock_state.json"
    EV.EVENTS=root/"logs"/"events.jsonl"
    TB.EVENTS=root/"brain"/"events.jsonl"; TB.TRADES=CC.TRADES
    (root/"brain").mkdir(parents=True, exist_ok=True)
    (root/"logs").mkdir(parents=True,exist_ok=True); (root/"challenge").mkdir(parents=True,exist_ok=True)
    CC.BOTS=[RaisingBot()]
    # bootstrap the clock so entries are permitted
    t0=NOW()-400
    for i in range(6):
        MS._OFFSET_CACHE.clear()
        fake.t = t0 + i*60
        MS.clock_state(fake, host_now=t0 + i*60, path=MS.CLOCK_STATE_PATH)
    fake.t = NOW()
    MS._OFFSET_CACHE.clear()
    if heal_st:
        _rc = MS.compute
        class _StateWithChallenge(dict):
            _cs = None
            def veto(self, r): return self._cs.veto(r)
            @property
            def equity(self): return self._cs.equity
            @property
            def daily_headroom(self): return self._cs.daily_headroom
            @property
            def total_headroom(self): return self._cs.total_headroom
        def _wrapped(*a, **k):
            d=_StateWithChallenge(_rc(*a, **k))
            d._cs = CC.ChallengeState(**CC.challenge_anchors(fake.account_info(), []))
            return d
        MS.compute = _wrapped
    if inject_at == "compute":
        # preflight also calls MS.compute; only the POST-ALLOCATION call passes session_start
        _real = MS.compute
        def _boom(*a, **k):
            if k.get("session_start") is not None: raise exc
            return _real(*a, **k)
        MS.compute = _boom
    elif inject_at:
        setattr(CC, inject_at, lambda *a, **k: (_ for _ in ()).throw(exc))
    argv=sys.argv[:]; sys.argv=["challenge_controller.py","--live-demo" if live else "--dry-run"]
    out=io.StringIO(); err=io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try: CC.main()
            except SystemExit: pass
    finally: sys.argv=argv
    log=""
    for f in (root/"logs").glob("controller-*.log"): log+=f.read_text(encoding="utf-8",errors="replace")
    events=[json.loads(l) for l in (EV.EVENTS.read_text(encoding="utf-8").splitlines()
            if EV.EVENTS.exists() else []) if l.strip()]
    trades=[json.loads(l) for l in (CC.TRADES.read_text(encoding="utf-8").splitlines()
            if CC.TRADES.exists() else []) if l.strip()]
    shutil.rmtree(d, ignore_errors=True)
    return dict(orders=fake.orders_sent, events=events, trades=trades,
                stdout=out.getvalue(), stderr=err.getvalue(), log=log)

print("="*78); print("TASK-0007 -- funded-candidate failure containment"); print("="*78)

# ---- E. HEALTHY PATH.
# The deployed release cannot execute ANY funded candidate: line 1516 rebinds `st` from the
# ChallengeState to a market_state dict inside the per-symbol loop, so line 1676's st.veto()
# raises AttributeError for every bot. That is root cause 2, and TASK-0007 does not fix it.
# To prove the CONTAINMENT does not break a working candidate, MS.compute returns a dict
# subclass that still answers veto/equity/headroom -- i.e. the desk as it will behave once the
# rebinding is corrected. Nothing in production is changed to make this pass.
h=run_cycle(heal_st=True)
ck("E healthy candidate still reaches order_send", len(h["orders"])==1, h["orders"])
ck("E healthy candidate writes exactly one ledger row", len(h["trades"])==1, len(h["trades"]))
ck("E healthy path emits no FUNDED_CANDIDATE_ERROR",
   not [e for e in h["events"] if e.get("event")=="FUNDED_CANDIDATE_ERROR"])

# ---- A/B/C. inject at three different stages
# heal_st on the SIZING case only: the real st.veto defect fires BEFORE sizing, so without
# healing it the recorded exception would be the production bug rather than the injected one.
CASES=[("compute", ValueError("could not convert string to float: 'lvl_asia_high'"), "MARKET_STATE", False),
       ("stop_geometry", AttributeError("stop geometry exploded"), "STOP_GEOMETRY", False),
       ("size_position", RuntimeError("boom during sizing"), "SIZING", True)]
for fn, exc, expect_stage, heal in CASES:
    r=run_cycle(inject_at=fn, exc=exc, heal_st=heal)
    err=[e for e in r["events"] if e.get("event")=="FUNDED_CANDIDATE_ERROR"]
    lbl=f"{type(exc).__name__}@{expect_stage}"
    ck(f"A/B/C {lbl}: ZERO order_send", len(r["orders"])==0, r["orders"])
    ck(f"A/B/C {lbl}: no ledger row written", len(r["trades"])==0, r["trades"])
    ck(f"A/B/C {lbl}: FUNDED_CANDIDATE_ERROR emitted", len(err)==1, len(err))
    if err:
        e=err[0]
        ck(f"A/B/C {lbl}: stage recorded", e.get("stage")==expect_stage, e.get("stage"))
        ck(f"A/B/C {lbl}: exception type recorded", e.get("exc_type")==type(exc).__name__, e.get("exc_type"))
        ck(f"A/B/C {lbl}: message recorded", str(exc) in (e.get("exc_message") or ""), e.get("exc_message"))
        ck(f"A/B/C {lbl}: bot+symbol+candidate id present",
           all(e.get(k) for k in ("bot","symbol","candidate_id","ts_london")), e)
    ck(f"A/B/C {lbl}: traceback preserved verbatim in stderr",
       "Traceback (most recent call last)" in r["stderr"] and type(exc).__name__ in r["stderr"])
    ck(f"A/B/C {lbl}: traceback also PERSISTED to the controller log",
       "Traceback (most recent call last)" in r["log"], r["log"][-200:])
    ck(f"A/B/C {lbl}: a no-trade reason survives for the reader",
       any(x.get("event")=="NO_TRADE" and "FUNDED_CANDIDATE_ERROR" in (x.get("reason") or "")
           for x in r["events"]))

# ---- D. the failure reason is not erased
r=run_cycle(inject_at="compute", exc=ValueError("x"))
ck("D failure does not silently disappear: an event names the stage and the exception",
   any(e.get("event")=="FUNDED_CANDIDATE_ERROR" and e.get("stage") and e.get("exc_type")
       for e in r["events"]))

# ---- stderr capture, independent of the containment path
ck("stderr is teed into the persistent controller log",
   "Traceback (most recent call last)" in r["log"])
import inspect, challenge_controller as _CC
src=inspect.getsource(_CC._start_logging)
ck("_start_logging tees BOTH streams", "sys.stdout = _Tee" in src and "sys.stderr = _Tee" in src)

# ---- G / structural: order_send and append_trade are inside the guarded block
import ast
tree=ast.parse(pathlib.Path("challenge_controller.py").read_text(encoding="utf-8"))
main=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="main"][0]
tries=[t for t in ast.walk(main) if isinstance(t,ast.Try)]
def span(t): return (t.lineno, max(x.lineno for x in ast.walk(t) if hasattr(x,"lineno")))
def guarded(n): return any(a<=n.lineno<=b for a,b in map(span,tries))
sends=[n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="order_send"]
apps=[n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="append_trade"]
ck("G every order_send in main() is inside the guarded block", all(map(guarded,sends)) and len(sends)==1)
ck("G every append_trade in main() is inside the guarded block", all(map(guarded,apps)) and len(apps)==2)

full=pathlib.Path("challenge_controller.py").read_text(encoding="utf-8")
ck("G time_exits and reconcile untouched by this task",
   "def time_exits(mt5, acct, bots, dry_run=False, magic=990001)" in full
   and "def reconcile(mt5, magic=990001)" in full)
ck("G broker SL/TP still never modified", "TRADE_ACTION_SLTP" not in full)

print("\n"+("ALL CANDIDATE-FAILURE TESTS PASSED" if not FAILED
            else f"FAILURES ({len(FAILED)}): "+"; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
