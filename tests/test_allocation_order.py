"""TASK-0004 -- caps must be enforced against CANDIDATES and REAL exposure, never hypotheses.

THE DEFECT. allocate() applied the correlated-group cap before any bot had been asked whether
a setup existed, and it started every cycle with an empty exposure book. So a bot that had
already refused the day's only setup still held its group's budget, and a bot holding an open
position consumed nothing. Measured on 2026-08-14: BOT_C and BOT_E were refused funding on
856/856 cycles without ever being asked to generate a signal.

WHAT THE FIXTURE PROVES. Lost OBSERVATION only. Nobody knows whether C or E had a valid or
profitable signal, because the desk never let them look. That limitation is encoded in the
fixture's own metadata so it cannot drift away from the test that reads it.
"""
import sys, json, pathlib; sys.path.insert(0, ".")
import desk as D
import challenge_controller as CC

FX = json.loads(pathlib.Path("tests/fixtures/friday_20260814_allocation.json")
                .read_text(encoding="utf-8"))


class CS:
    def __init__(s, v=None): s.v = v
    def veto(s, r): return s.v


class Bot:
    shadow = False
    risk_override = None
    def __init__(s, sid, symbol, playbook, risk=0.0010):
        s.strategy_id, s.symbol, s.playbook, s.risk = sid, symbol, playbook, risk


class Pos:
    def __init__(s, ticket, symbol, magic=990001):
        s.ticket, s.symbol, s.magic = ticket, symbol, magic


class FakeMT5:
    def __init__(s, positions=(), orders=()): s._p, s._o = list(positions), list(orders)
    def positions_get(s, **k): return s._p
    def orders_get(s, **k): return s._o


TREND = {"opportunities": ["TREND_UP", "EXPANSION"]}


def ledger(*rows):
    return [dict(kind="intent", **r) for r in rows]


# ---- 1. no candidates at all -> nobody is funded, and nobody holds budget
bots = [Bot("A", "US500", "BREAKOUT"), Bot("C", "XAUUSD", "BREAKOUT")]
opp = {b.symbol: TREND for b in bots}
p = D.allocate(bots, opp, lambda b: b.risk, CS(), candidates=set())
assert p["total_risk"] == 0.0, p["total_risk"]
assert all(d.get("no_candidate") for d in p["decisions"].values()), p["decisions"]
print("  1. zero candidates -> 0.000% allocated, all marked no_candidate")

# ---- 2. THE FRIDAY REPRODUCTION. A produces nothing; C and E do. Under the old ordering A
# held the BREAKOUT cap and C/E were refused. Now the budget follows the candidates.
fbots = [Bot(b["strategy_id"], b["symbol"], b["playbook"], b["risk_pct"])
         for b in FX["cycle"]["bots"]]
fopp = FX["cycle"]["opportunities_by_symbol"]
cands = {b["strategy_id"] for b in FX["cycle"]["bots"] if b["produces_signal"]}
assert cands == {"BOT_C", "BOT_E"}
fp = D.allocate(fbots, fopp, lambda b: b.risk, CS(), candidates=cands)
assert fp["decisions"]["BOT_A"].get("no_candidate") is True
assert fp["decisions"]["BOT_A"]["risk"] == 0.0, "the bot with no setup still held budget"
funded = [s for s, d in fp["decisions"].items() if d["allow"]]
assert funded and set(funded) <= cands, funded
print(f"  2. Friday fixture: A consumes nothing, funded={funded} "
      f"(fixture proves lost observation only)")

# ---- 3. the fixture must keep saying what it does NOT claim
md = FX["_metadata"]
assert md["immutable"] is True
assert "profitable" in " ".join(md["does_not_claim"])
assert md["measured"]["candidates_produced_by_c_or_e"] is None
print("  3. fixture metadata still disclaims profitability and validity")

# ---- 4. exposure already LIVE consumes the group cap (it used to consume nothing)
live_full = {"BREAKOUT": D.GROUP_CAP}
p4 = D.allocate(bots, opp, lambda b: b.risk, CS(),
                candidates={"C"}, open_group_risk=live_full)
assert not p4["decisions"]["C"]["allow"], p4["decisions"]["C"]
assert "group at" in p4["decisions"]["C"]["reason"]
print("  4. open BREAKOUT exposure at cap blocks a new BREAKOUT candidate")

# ---- 5. with the book empty, the same candidate IS funded -- proving 4 came from exposure
p5 = D.allocate(bots, opp, lambda b: b.risk, CS(), candidates={"C"}, open_group_risk={})
assert p5["decisions"]["C"]["allow"], p5["decisions"]["C"]
print("  5. same candidate funded when nothing is live -- 4 was exposure, not fit")

# ---- 6. INVARIANT A: CORRELATION_CAP may appear ONLY after a candidate exists
import desk_events as EV
for sid, d in fp["decisions"].items():
    if EV.reason_code(d.get("reason", "")) == "CORRELATION_CAP":
        assert sid in cands, f"{sid} capped without ever producing a candidate"
for sid, d in p["decisions"].items():          # the zero-candidate cycle
    assert EV.reason_code(d.get("reason", "")) != "CORRELATION_CAP", (sid, d)
print("  6. INVARIANT A holds: no CORRELATION_CAP without a candidate")

# ---- 7. legacy call (candidates=None) is unchanged, so eligibility can still be asked alone
p7 = D.allocate(bots, opp, lambda b: b.risk, CS())
assert any(d["allow"] for d in p7["decisions"].values())
assert not any("no_candidate" in d for d in p7["decisions"].values())
print("  7. candidates=None preserves the pre-existing behaviour")

# ---- 8. desk_exposure attributes live positions to groups through the ledger
known = {b.strategy_id: b for b in bots}
e8 = CC.desk_exposure(FakeMT5([Pos(11, "US500")]),
                      ledger({"intent_id": "i1", "ticket": 11, "strategy_id": "A",
                              "risk_pct": 0.0010}), known)
assert e8["faults"] == [], e8["faults"]
assert e8["per_group"] == {"BREAKOUT": 0.0010}, e8["per_group"]
print(f"  8. live position attributed: {e8['per_group']}")

# ---- 9. a broker position the ledger cannot explain is a FAULT, never zero
e9 = CC.desk_exposure(FakeMT5([Pos(99, "XAUUSD")]), ledger(), known)
assert [f["code"] for f in e9["faults"]] == ["EXPOSURE_UNRECONCILED"], e9["faults"]
print("  9. unattributable broker position -> EXPOSURE_UNRECONCILED (fails closed)")

# ---- 10. a ledger row naming a strategy this desk does not run is a FAULT
e10 = CC.desk_exposure(FakeMT5([Pos(12, "US500")]),
                       ledger({"intent_id": "i2", "ticket": 12, "strategy_id": "GONE",
                               "risk_pct": 0.0010}), known)
assert [f["code"] for f in e10["faults"]] == ["UNKNOWN_STRATEGY"], e10["faults"]
print(" 10. ledger row for an unknown strategy -> UNKNOWN_STRATEGY (fails closed)")

# ---- 11. any pending order on the desk magic is a FAULT: this desk only sends market orders
e11 = CC.desk_exposure(FakeMT5([], [Pos(77, "US500")]), ledger(), known)
assert [f["code"] for f in e11["faults"]] == ["UNEXPECTED_PENDING_ORDER"], e11["faults"]
print(" 11. pending order on the desk magic -> UNEXPECTED_PENDING_ORDER (fails closed)")

# ---- 12. two open ledger rows claiming one ticket is a FAULT
e12 = CC.desk_exposure(FakeMT5([Pos(13, "US500")]),
                       ledger({"intent_id": "i3", "ticket": 13, "strategy_id": "A",
                               "risk_pct": 0.0010},
                              {"intent_id": "i4", "ticket": 13, "strategy_id": "C",
                               "risk_pct": 0.0010}), known)
assert "DUPLICATE_TICKET" in [f["code"] for f in e12["faults"]], e12["faults"]
print(" 12. one ticket claimed twice -> DUPLICATE_TICKET (fails closed)")

# ---- 13. LEDGER_AHEAD_OF_BROKER is reported explicitly, counts as zero, is NOT a fault and is
# NOT silently normalised into agreement. reconcile() runs earlier in the same cycle.
e13 = CC.desk_exposure(FakeMT5([]),
                       ledger({"intent_id": "i5", "ticket": 14, "strategy_id": "A",
                               "risk_pct": 0.0010}), known)
assert e13["ledger_ahead_of_broker"] == [14], e13
assert e13["faults"] == [], e13["faults"]
assert e13["per_group"] == {}, e13["per_group"]
print(" 13. LEDGER_AHEAD_OF_BROKER recorded explicitly, zero exposure, not a fault")

# ---- 14. closed rows are not exposure
e14 = CC.desk_exposure(FakeMT5([]),
                       ledger({"intent_id": "i6", "ticket": 15, "strategy_id": "A",
                               "risk_pct": 0.0010}) +
                       [{"kind": "close", "intent_id": "i6", "ticket": 15}], known)
assert e14["ledger_ahead_of_broker"] == [] and e14["faults"] == [], e14
print(" 14. a closed intent is neither exposure nor a disagreement")

# ---- 15. INVARIANT B: at every order_send, live + sent-this-cycle + this order <= caps
g, t = {"BREAKOUT": 0.0010}, 0.0010          # 0.0010 already live
ok, why = CC.exposure_gate(g, t, "BREAKOUT", 0.0005)
assert ok, why                                # 0.0015 == group cap, allowed
ok2, why2 = CC.exposure_gate(g, t, "BREAKOUT", 0.0006)
assert not ok2 and "group cap" in why2, why2  # 0.0016 > cap, blocked
print(f" 15. INVARIANT B group edge: 0.0015 allowed, 0.0016 blocked -- {why2}")

# ---- 16. the total cap binds even when every individual group is under its own cap
g16 = {f"G{i}": 0.0015 for i in range(5)}     # 0.0075 == total cap, five groups all legal
ok3, why3 = CC.exposure_gate(g16, sum(g16.values()), "G_NEW", 0.0001)
assert not ok3 and "total cap" in why3, why3
print(f" 16. INVARIANT B total edge: blocked at the desk cap -- {why3}")

# ---- 17. the gate accumulates WITHIN a cycle: a second order cannot re-spend the first's room
sent, tot = {}, 0.0
allowed = []
for i in range(4):
    ok4, _ = CC.exposure_gate(sent, tot, "BREAKOUT", 0.0005)
    if not ok4:
        break
    sent["BREAKOUT"] = sent.get("BREAKOUT", 0.0) + 0.0005
    tot += 0.0005
    allowed.append(i)
assert allowed == [0, 1, 2], allowed          # 3 x 0.0005 = 0.0015, the 4th must be refused
print(f" 17. gate accumulates within the cycle: {len(allowed)} orders then blocked")

# ---- 18. the gate and the allocator read ONE definition of capacity
import inspect
sigd = inspect.signature(D.allocate)
assert sigd.parameters["group_cap"].default is D.GROUP_CAP
assert sigd.parameters["total_cap"].default is D.TOTAL_CAP
print(" 18. allocator and pre-send gate share desk.GROUP_CAP / desk.TOTAL_CAP")

print("\nALL ALLOCATION-ORDER TESTS PASSED")
