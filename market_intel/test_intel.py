"""PHASE 701 tests. The critical one: the engine CANNOT place a trade."""
import sys, os, glob, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd, numpy as np
from datetime import datetime, timezone
from market_intel import state, calendar_feed as cal, opportunity, engine

def _bars(n=400):
    idx=pd.date_range("2026-08-12 06:00",periods=n,freq="5min",tz="UTC")
    p=pd.Series(1.10+np.cumsum(np.random.RandomState(0).randn(n))*0.0002,index=idx)
    return pd.DataFrame({"open":p,"high":p+0.0004,"low":p-0.0004,"close":p})
def _d1(n=30):
    idx=pd.date_range("2026-07-14",periods=n,freq="D",tz="UTC")
    p=pd.Series(1.10+np.cumsum(np.random.RandomState(1).randn(n))*0.002,index=idx)
    return pd.DataFrame({"open":p,"high":p+0.004,"low":p-0.004,"close":p})

def test_package_cannot_place_orders():
    """STRUCTURAL: no module in market_intel may reference an order-submission call."""
    banned=["order_send","place_order","TRADE_ACTION_DEAL","positions_get"]
    for f in glob.glob(os.path.join(os.path.dirname(__file__),"*.py")):
        if os.path.basename(f).startswith("test_"): continue   # test files assert on the banned strings
        src=open(f).read()
        for b in banned:
            assert b not in src, f"{os.path.basename(f)} references {b}"

def test_no_opportunity_before_actual():
    st=state.classify("EURUSD",_bars(),_d1())
    e=cal.Event("1","US CPI y/y","USD","2026-08-12T12:30:00+00:00","high",previous=3.1,forecast=3.0)
    assert opportunity.from_release(e,st) is None

def test_opportunity_after_actual_has_all_fields():
    st=state.classify("EURUSD",_bars(),_d1())
    e=cal.Event("1","US CPI y/y","USD","2026-08-12T12:30:00+00:00","high",previous=3.1,forecast=3.0,actual=3.4)
    o=opportunity.from_release(e,st)
    for f in ("instrument","direction","confidence","expected_volatility","economic_reasoning",
              "technical_confirmation","regime_compatibility","kill_zone_alignment","risk_estimate",
              "stop_suggestion","target_suggestion","expected_holding_period",
              "evidence_supporting","evidence_contradicting"):
        assert hasattr(o,f), f

def test_pipeline_fails_closed_when_components_unwired():
    st=state.classify("EURUSD",_bars(),_d1())
    e=cal.Event("1","CPI","USD","2026-08-12T12:30:00+00:00","high",previous=3.1,forecast=3.0,actual=3.4)
    o=opportunity.from_release(e,st)
    d=engine.evaluate_through_pipeline(o)          # belief/guardian not supplied
    assert d["decision"]=="RESEARCH_ONLY" and o.status=="REJECTED"

def test_pre_event_report_has_no_direction():
    st=state.classify("EURUSD",_bars(),_d1())
    e=cal.Event("1","NFP","USD","2026-08-12T12:30:00+00:00","high",previous=150,forecast=175)
    r=engine.pre_event_report(e,st)
    assert r["direction"] is None

def test_kill_zone_and_session_classification():
    ss=state.active_sessions(datetime(2026,8,12,13,0,tzinfo=timezone.utc))
    assert ss["session"]=="newyork" and "ny_am_kz" in ss["kill_zones"]

if __name__=="__main__":
    fns=[v for k,v in list(globals().items()) if k.startswith("test_")]; p=0
    for fn in fns:
        try: fn(); p+=1; print("PASS",fn.__name__)
        except AssertionError as e: print("FAIL",fn.__name__,e)
        except Exception as e: print("ERR ",fn.__name__,repr(e))
    print(f"\n{p}/{len(fns)} PHASE 701 guarantees proven")
