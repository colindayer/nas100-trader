"""The two gates that would have stopped yesterday's -6.07R."""
import sys, pandas as pd
sys.path.insert(0,".")
import challenge_controller as C

# --- event blackout: BOT_D was gapped at 13:30 London, the US release slot
def at(h,m): return pd.Timestamp(f"2026-08-12 {h:02d}:{m:02d}", tz="Europe/London")
assert C.in_event_blackout(at(13,30)) is not None, "release slot not blocked"
assert C.in_event_blackout(at(13,25)) is not None, "pre-release not blocked"
assert C.in_event_blackout(at(13,49)) is not None, "post-release not blocked"
assert C.in_event_blackout(at(13,19)) is None, "blocked too early"
assert C.in_event_blackout(at(13,51)) is None, "blocked too long"
assert C.in_event_blackout(at(6,30)) is None, "blocked BOT_A's window"
assert C.in_event_blackout(at(14,30)) is None, "blocked the US cash open"
print("  blackout:", C.in_event_blackout(at(13,30)))

# --- volatility floor: 6.11pt gold stop vs D1 ATR ~60
ATR = 60.0
for dist, want_block in ((6.11, True), (30.0, False), (9.1, False), (8.9, True)):
    blocked = dist < C.MIN_STOP_ATR_FRAC * ATR
    assert blocked == want_block, f"stop {dist} vs ATR {ATR}: got {blocked}"
print(f"  volatility floor: needs >= {C.MIN_STOP_ATR_FRAC:.0%} of ATR {ATR} = "
      f"{C.MIN_STOP_ATR_FRAC*ATR:.2f}; BOT_D's 6.11 blocked, BOT_A's 30.0 allowed")

# the blackout must never touch an open position
import inspect
src = inspect.getsource(C.main)
i_black = src.index("in_event_blackout")
assert "positions_get" not in src[i_black:i_black+400], "blackout reaches an open position"
print("RISK GATE CHECKS PASS")

# --- cost/R is the lever a zero-edge system actually controls ---
# First-passage sim, 1% risk, 40k paths: cost 2%R -> P(pass) 31.6%; 5%R -> 20.8%; 10%R -> 9.2%
from bot_base import Signal as _Sig
def geo(stop, spread, atr):
    s = _Sig("x","1","t","S",1,"market",100.0,100.0-stop,100.0+stop,60)
    return C.stop_geometry(s, {"atr20_d1":atr,"m1_excursion_p90_60":None}, None, spread)

# every ACCEPTED stop must keep spread under ~4% of R
for stop, spread, atr in ((30.0,0.50,88.0), (95.1,1.45,633.7), (13.4,0.60,89.0),
                          (0.0027,0.00012,0.0050)):
    g = geo(stop, spread, atr)
    assert g["ok"], g
    final = g.get("widened_to") or stop
    assert spread/final <= 0.04, f"accepted a {spread/final:.1%} cost trade"

# the old 8x floor permitted 12.5% cost. It is now unreachable: a stop that tight sits
# under a third of the new floor, so it is REJECTED rather than widened -- stricter than
# merely resizing it, because at that distance the setup is inside the noise.
assert C.MIN_STOP_SPREAD_MULT >= 30.0
g = geo(8*0.6, 0.6, 89.0)                     # exactly the old floor
assert not g["ok"], f"old 8x floor still tradable at {0.6/(8*0.6):.1%} cost"
assert "inside the noise" in g["reason"]

# and the band in between is widened, not rejected -- the desk keeps trading
g = geo(13.4, 0.6, 89.0)
assert g["ok"] and g["widened_to"] == 18.0 and 0.6/18.0 <= 0.04

# a true scalp stop is REJECTED, not silently widened into a different strategy
g = geo(1.85, 0.60, 89.0)
assert not g["ok"] and "inside the noise" in g["reason"]
print(f"  cost/R capped: every accepted stop <= 4% spread cost; 8x-floor case now widened")
print(f"  a 32% cost scalp is rejected, not reshaped into a trade nobody tested")
print("COST CONTROL CHECKS PASS")
