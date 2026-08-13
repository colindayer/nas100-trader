"""VOID needs a provable defect. A losing trade that ran as specified is EVIDENCE."""
import sys; sys.path.insert(0,".")
import head_trader as HT
from challenge_controller import BOTS
byid = {b.strategy_id: b for b in BOTS}

FULL = {"d1_regime":"up","h4_regime":"up","h1_regime":"up","atr20_d1":88.0,
        "ms_labels":["TREND_UP"]}
def trade(**kw):
    base = {"strategy_id":"BOT_A_gold_0630_breakout","symbol":"XAUUSD",
            "timestamp":"2026-08-14T07:15:00+01:00","market_state":dict(FULL),
            "risk_pct":0.001,"account_equity":100000.0,"net":-100.0,"R":-1.0,
            "retcode":10009,"ticket":123,"outcome":"stop","holding_minutes":45}
    base.update(kw); return base

# a LOSS that ran exactly as specified is VALID
v, why = HT.validity(trade(), byid)
assert v == "VALID", why
print(f"  clean -1R loss in-session -> {v}  (a loss is evidence)")

# missing regime -> VOID
v, why = HT.validity(trade(market_state={**FULL, "d1_regime": None}), byid)
assert v == "VOID" and "d1_regime" in why[0], why
print(f"  missing d1_regime -> {v}: {why[0]}")

# wrong session (the 3h clock bug) -> VOID
v, why = HT.validity(trade(timestamp="2026-08-14T03:30:00+01:00"), byid)
assert v == "VOID" and "outside its declared" in why[0], why
print(f"  03:30 entry on a 06:30 bot -> {v}: {why[0]}")

# risk overrun (BOT_D) -> VOID
v, why = HT.validity(trade(net=-300.0, R=-3.0), byid)
assert v == "VOID" and "planned" in why[0], why
print(f"  3x planned risk -> {v}: {why[0]}")

# rejected order is never a trade
v, why = HT.validity(trade(retcode=10027, ticket=None), byid)
assert v == "VOID" and "not a completed fill" in " ".join(why)
print(f"  retcode 10027 -> {v} (a rejection is not a trade)")

# a BIG loss with everything correct is STILL valid
v, why = HT.validity(trade(net=-99.0, R=-0.99), byid)
assert v == "VALID", why
# and a win is judged by the same rule, not a softer one
v2, _ = HT.validity(trade(net=200.0, R=2.0, outcome="target"), byid)
assert v2 == "VALID"
print(f"  losses and wins judged identically -> {v} / {v2}")
print("VALIDITY CHECKS PASS")
