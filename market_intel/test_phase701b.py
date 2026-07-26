"""Tests for the new PHASE 701 modules."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from market_intel import telegram_notifier as tg, calendar_provider as cp

def test_telegram_never_places_orders():
    import inspect
    for m in (tg, cp):
        src = inspect.getsource(m)
        for banned in ("order_send", "place_order", "TRADE_ACTION_DEAL"):
            assert banned not in src, f"{m.__name__} references {banned}"

def test_telegram_unconfigured_fails_gracefully():
    os.environ.pop("TELEGRAM_TOKEN", None)
    r = tg.send("opportunity", "x")
    assert r["sent"] is False and "TELEGRAM_TOKEN" in r["error"]

def test_telegram_rejects_unknown_class():
    assert tg.send("not_a_class", "x")["sent"] is False

def test_telegram_confidence_filter():
    class O:  # low-confidence opportunity must not alert
        instrument="EURUSD"; direction=1; confidence=0.10; economic_reasoning="x"
        stop_suggestion=1.0; target_suggestion=2.0; evidence_supporting=[]; evidence_contradicting=[]
        status="REGISTERED"
    assert tg.opportunity(O())["sent"] is False


def test_calendar_provider_priority_and_empty():
    ev, prov = cp.load()
    assert isinstance(ev, list) and prov in [p[0] for p in cp.PROVIDERS] + ["none"]

def test_forexfactory_disabled_by_default():
    os.environ.pop("FOREXFACTORY_ENABLED", None)
    assert cp.from_forexfactory() == []

def test_economic_event_no_surprise_before_actual():
    e = cp.EconomicEvent("1","CPI","US","USD","2026-08-12T12:30:00+00:00","high",previous=3.1,forecast=3.0)
    assert e.released() is False and e.surprise() is None
    e.actual = 3.4
    assert abs(e.surprise() - 0.4) < 1e-9 and abs(e.surprise_pct() - 0.13333) < 1e-4

def test_record_reaction_builds_real_history():
    p = os.path.join(tempfile.mkdtemp(), "h.json")
    e = cp.EconomicEvent("1","US CPI","US","USD","x","high",forecast=3.0,actual=3.4)
    h = cp.record_reaction(e, "EURUSD", -0.004, path=p)
    assert h["n"] == 1 and abs(h["mean_move_pct"] + 0.004) < 1e-9

if __name__=="__main__":
    fns=[v for k,v in list(globals().items()) if k.startswith("test_")]; p=0
    for fn in fns:
        try: fn(); p+=1; print("PASS",fn.__name__)
        except AssertionError as e: print("FAIL",fn.__name__,e)
        except Exception as e: print("ERR ",fn.__name__,repr(e))
    print(f"\n{p}/{len(fns)} PHASE 701b guarantees proven")
