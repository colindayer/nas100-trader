"""FTMO headroom must reflect real drawdown. It read 'full' at -$520."""
import sys, types, json, tempfile, pathlib
sys.path.insert(0,".")
import pandas as pd
import challenge_controller as C

d = pathlib.Path(tempfile.mkdtemp()); C.DATA=d; C.TRADES=d/"t.jsonl"; C.STATE=d/"s.json"
A = lambda bal,eq: types.SimpleNamespace(balance=bal, equity=eq)
today = pd.Timestamp.now(tz="Europe/London").date().isoformat()
trades = [{"kind":"close","net":-520.13,"intent_id":"x"},
          {"intent_id":"x","timestamp":today,"ticket":1,"risk_pct":0.001}]

# the real situation: balance 99479.87 after -520.13 realised
st = C.ChallengeState(**C.challenge_anchors(A(99479.87, 99479.87), trades))
assert abs(st.starting_balance - 100000.0) < 0.01, st.starting_balance
assert abs(st.profit_pct + 0.0052013) < 1e-6, st.profit_pct
assert abs(st.total_headroom - 0.0947987) < 1e-6, st.total_headroom
print(f"  anchored: start {st.starting_balance:.2f}  profit {st.profit_pct:+.4%}  "
      f"total headroom {st.total_headroom:.4%}  (was reporting 10.0000%)")

# anchor must NOT drift when equity moves
st2 = C.ChallengeState(**C.challenge_anchors(A(95000.0, 95000.0), trades))
assert abs(st2.starting_balance - 100000.0) < 0.01, "anchor drifted with the account"
assert abs(st2.profit_pct + 0.05) < 1e-9
assert abs(st2.total_headroom - 0.05) < 1e-9
print(f"  at 95k: profit {st2.profit_pct:+.2%}  total headroom {st2.total_headroom:.2%}")

# the veto must now actually bite near the limit
st3 = C.ChallengeState(**C.challenge_anchors(A(90500.0, 90500.0), trades))
v = st3.veto(0.001)
assert v is not None, "veto silent at -9.5% total drawdown"
print(f"  at -9.5%: VETO -> {v}")

# intraday loss must consume daily headroom
C.STATE.write_text(json.dumps({"starting_balance":100000.0,"day":today,
                               "day_start_equity":100000.0}))
st4 = C.ChallengeState(**C.challenge_anchors(A(97000.0, 97000.0), trades))
assert abs(st4.daily_headroom - 0.02) < 1e-9, st4.daily_headroom
assert st4.veto(0.001) is None and st4.veto(0.011) is not None
print(f"  -3% on the day: daily headroom {st4.daily_headroom:.2%} (was 5.00%)")

# open risk must be counted, not assumed zero
assert abs(st.open_risk_pct - 0.0) < 1e-9   # intent x is closed
open_only = [{"intent_id":"y","timestamp":today,"ticket":2,"risk_pct":0.002}]
st5 = C.ChallengeState(**C.challenge_anchors(A(99479.87,99479.87), open_only))
assert abs(st5.open_risk_pct - 0.002) < 1e-9, st5.open_risk_pct
print(f"  open risk tracked: {st5.open_risk_pct:.3%}")
print("ANCHOR CHECKS PASS")
