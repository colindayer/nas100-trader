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
