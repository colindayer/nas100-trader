"""Acceptance: trading-critical faults stop entries, auxiliary faults never do,
and no event disappears into stdout."""
import sys, json, tempfile, pathlib, types
sys.path.insert(0,".")
import desk_events as EV, desk_orchestrator as ORC

d = pathlib.Path(tempfile.mkdtemp())
EV.EVENTS = d/"events.jsonl"
ORC.LOGS = d; ORC.TRADES = d/"trades.jsonl"; ORC.BRAIN = d/"brain.jsonl"
ORC.REVIEW_QUEUE = d/"queue"

# ---------- 1. reason codes are countable, and gaps are visible ----------
cases = {
 "outside window: 22:00 London, opens 08:00 closes 16:30": "OUTSIDE_WINDOW",
 "first break already happened at 06:51 (128m ago) -- not chasing a re-test": "FIRST_BREAK_ALREADY_OCCURRED",
 "regime TRANSITION is structurally wrong for this bot": "REGIME_MISMATCH",
 "BREAKOUT group at 0.142% of 0.15% cap -- correlated exposure": "CORRELATION_CAP",
 "RISK MANAGER veto: daily headroom 0.1% too thin": "RISK_VETO",
 "DATA_INTEGRITY -- not sending. Missing d1_regime": "MISSING_MARKET_STATE",
 "stop 1.85 is under a third of the spread floor -- inside the noise": "STOP_INSIDE_NOISE",
 "something nobody has ever written before": "UNMAPPED",
}
for text, want in cases.items():
    got = EV.reason_code(text)
    assert got == want, f"{text[:40]!r} -> {got}, want {want}"
print(f"  {len(cases)} reason codes map correctly; unknown text -> UNMAPPED (visible, not hidden)")

# ---------- 2. the field 2026-08-14 lacked ----------
bot = types.SimpleNamespace(strategy_id="BOT_A_gold_0630_breakout", playbook="BREAKOUT",
                            symbol="XAUUSD")
EV.no_trade(bot, "2026-08-15T06:51:00+01:00",
            "first break already happened at 06:51 (1m ago) -- not chasing a re-test",
            funded=True, bid=4400.0, ask=4400.5, beyond_level=True, level=4399.0,
            cycle_gap_s=88.0)
e = EV.read()[-1]
assert e["reason_code"] == "FIRST_BREAK_ALREADY_OCCURRED"
assert e["beyond_level"] is True and e["funded"] is True and e["cycle_gap_s"] == 88.0
print(f"  no-trade event carries funded/beyond_level/cycle_gap -> the sampling race is now decidable")

# ---------- 3. a fallback can never be silent ----------
EV.fallback("anchor", "broker deposit", "ledger reconstruction", "history_deals_get returned None")
f = EV.read()[-1]
assert f["event"] == "FALLBACK" and f["preferred"] == "broker deposit"
print("  fallbacks emit an explicit event")

# ---------- 4. observability failure must not raise ----------
EV.EVENTS = pathlib.Path("/nonexistent/dir/that/cannot/exist/events.jsonl")
EV.emit("test", "SHOULD_NOT_RAISE", x=1)          # must degrade, not crash
EV.EVENTS = d/"events.jsonl"
print("  an unwritable event log degrades quietly and NEVER stops the desk")

# ---------- 5. health: heartbeat is the critical signal ----------
import time
(d/".last_cycle").write_text(str(time.time()))
h = ORC.health()
assert not any("not firing" in f for f in h["faults"]), h["faults"]
(d/".last_cycle").write_text(str(time.time() - 3600))
h2 = ORC.health()
assert any("not firing" in f for f in h2["faults"]), h2["faults"]
assert h2["status"] == ORC.RED
print(f"  stale heartbeat -> RED: {[f for f in h2['faults'] if 'firing' in f][0]}")

# ---------- 6. evidence completeness ----------
rows = [
 {"intent_id":"a","strategy_id":"BOT_A","retcode":10009,"ticket":1,
  "market_state":{"d1_regime":"up"},"risk_pct":0.001,"account_equity":100000.0},
 {"kind":"close","intent_id":"a","exit":4400.0,"net":-100.0,"R":-1.0},
 {"intent_id":"b","strategy_id":"BOT_B","retcode":10027,"ticket":None,"market_state":{}},
]
ORC.TRADES.write_text("\n".join(json.dumps(r) for r in rows)+"\n", encoding="utf-8")
m = ORC.evidence()
assert m["fills"] == 1 and m["rejections"] == 1 and m["closes"] == 1
assert m["fills_reconciled_pct"] == 100.0
assert m["exits_reconstructed_pct"] == 100.0
assert m["market_state_attached_pct"] == 50.0     # the rejected one carries none
print(f"  evidence: fills {m['fills']}, reconciled {m['fills_reconciled_pct']}%, "
      f"state attached {m['market_state_attached_pct']}% (incomplete is VISIBLE)")

# ---------- 7. a rejection is never a trade ----------
assert m["orders_attempted"] == 2 and m["fills"] == 1
print("  a rejected order counts as an attempt, never as a trade")

# ---------- 8. report degrades to FIX PROVEN DEFECT on incompleteness ----------
rep = ORC.validation_report(h2, m)
assert "DESK STATUS: **RED**" in rep and "FIX PROVEN DEFECT" in rep
assert "market_state_attached_pct | 50.0%" in rep and "FIX INFRASTRUCTURE" in rep
print("  incomplete instrumentation -> FIX PROVEN DEFECT, not a strategy change")

# ---------- 9. auxiliary failure is fail-OPEN ----------
ORC._run = lambda *a, **k: (1, "fatal: could not read Username")   # git broken
s = ORC.sync()
assert "unreachable" in str(s) or "not a git" in str(s), s
print(f"  git unreachable -> recorded, trading unaffected: {list(s.values())[0][:44]}")
print("ORCHESTRATOR ACCEPTANCE PASS")
