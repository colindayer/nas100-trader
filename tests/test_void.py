"""Voiding stops the Brain LEARNING from a trade. It must never delete one."""
import sys, json, tempfile, pathlib
sys.path.insert(0,".")
import trading_brain as TB

d = pathlib.Path(tempfile.mkdtemp())
TB.TRADES = d/"t.jsonl"; TB.BRAIN = d/"b"; TB.EVENTS = d/"b"/"e.jsonl"
rows = []
for i, r in enumerate([-1.0, -1.0, 2.0]):
    rows.append({"intent_id":f"i{i}","strategy_id":"BOT_A","timestamp":"2026-08-12T06:30"})
    rows.append({"kind":"close","intent_id":f"i{i}","strategy_id":"BOT_A","R":r})
TB.TRADES.write_text("\n".join(json.dumps(r) for r in rows)+"\n", encoding="utf-8")

before = TB.closed_trades()
assert len(before) == 3
b0 = TB.belief("BOT_A", 0.15, 30)
print(f"  before void: n={b0['n']} exp {b0['exp']:+.3f}")

TB.emit("evidence_voided", intent_ids=["i0","i1"],
        reason="broker clock 3h off -- traded the Asian session while calling itself London")
after = TB.closed_trades()
assert len(after) == 1 and after[0]["R"] == 2.0, after
b1 = TB.belief("BOT_A", 0.15, 30)
print(f"  after void:  n={b1['n']} exp {b1['exp']:+.3f}  (2 trades no longer taught anything)")

# THE LEDGER MUST BE UNTOUCHED
raw = [json.loads(l) for l in TB.TRADES.read_text(encoding="utf-8").splitlines()]
assert len(raw) == 6, "voiding deleted ledger rows"
assert len(TB.closed_trades(include_voided=True)) == 3, "voided trades unrecoverable"
print(f"  ledger still holds all {len(raw)} rows; include_voided recovers all 3")

# the reason must be retrievable, not just the fact
v = TB.voided_intents()
assert v["i0"].startswith("broker clock"), v
print(f"  reason preserved: {v['i0'][:52]}...")

# voiding twice must not corrupt anything
TB.emit("evidence_voided", intent_ids=["i0"], reason="duplicate")
assert len(TB.closed_trades()) == 1
print("VOID CHECKS PASS")
