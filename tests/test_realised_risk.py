"""TASK-0006 -- executable volume may never imply more risk than was requested.

Every number below is the MEASURED FTMO-Demo specification read from account 1514166963 on
2026-08-16, not a convention. volume_min is 0.01 on all four traded symbols and never binds;
the defect was volume_step granularity, which on XAUUSD is $14.10 per 0.01 lot at the 14.10
floor stop -- 28.4% of a 0.05% budget, so round-to-nearest carried +/-14.2%.
"""
import sys, types, math
sys.path.insert(0, ".")
import challenge_controller as CC
import desk as D

EQ = 99431.72                      # live equity at measurement time

SPEC = {   # measured, not remembered
 "XAUUSD":     dict(volume_min=0.01, volume_step=0.01, volume_max=100.0,
                    trade_tick_value=1.0,  trade_tick_size=0.01,  trade_contract_size=100.0),
 "EURUSD":     dict(volume_min=0.01, volume_step=0.01, volume_max=50.0,
                    trade_tick_value=1.0,  trade_tick_size=1e-05, trade_contract_size=100000.0),
 "US100.cash": dict(volume_min=0.01, volume_step=0.01, volume_max=1000.0,
                    trade_tick_value=0.01, trade_tick_size=0.01,  trade_contract_size=1.0),
 "US500.cash": dict(volume_min=0.01, volume_step=0.01, volume_max=1000.0,
                    trade_tick_value=0.01, trade_tick_size=0.01,  trade_contract_size=1.0),
}
PRICE = {"XAUUSD": 4375.0, "EURUSD": 1.09, "US100.cash": 24000.0, "US500.cash": 6400.0}
def info(sym): return types.SimpleNamespace(**SPEC[sym])

# bot, symbol, intended risk, stop distance as measured/derived on 2026-08-16
CASES = [
 ("BOT_A", "XAUUSD",     0.0010, 30.0),        # fixed stop, never widened (floor is 14.10)
 ("BOT_B", "US100.cash", 0.0010, 36.005),
 ("BOT_C", "US500.cash", 0.0005, 3.25),
 ("BOT_D", "XAUUSD",     0.0005, 14.10),       # widened to the floor when the range is tight
 ("BOT_E", "EURUSD",     0.0005, 0.000215),
 ("BOT_F", "US100.cash", 0.0005, 26.69),
 ("BOT_G", "US100.cash", 0.0005, 594.583),
 ("BOT_H", "XAUUSD",     0.0005, 14.10),       # 0.15*ATR=13.49 < floor, so ALWAYS the floor
]

FAILED = []
def ck(n, c, d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}" + ("" if c else f"   <- {d}"))
    if not c: FAILED.append(n)

def old_size(eq, risk, stop, i):
    """The RC1 behaviour, reproduced here so the before/after is measured, not asserted."""
    per = stop * (i.trade_tick_value / i.trade_tick_size)
    vol = max(i.volume_min, round((eq * risk) / per / i.volume_step) * i.volume_step)
    return vol, vol * per / eq

print("=" * 100)
print("BEFORE / AFTER -- measured FTMO specs, account 1514166963")
print("=" * 100)
h = f"{'BOT':<7}{'SYMBOL':<12}{'intend%':>9}{'stop':>10}{'old vol':>9}{'old%':>9}{'old x':>7}{'new vol':>9}{'new%':>9}{'new x':>7}"
print(h); print("-" * len(h))
after = {}
for bot, sym, risk, stop in CASES:
    i = info(sym)
    ov, opct = old_size(EQ, risk, stop, i)
    s = CC.size_position(EQ, risk, stop, i, PRICE[sym])
    nv = s["volume"] or 0.0
    npct = s["realised_risk_pct"] or 0.0
    after[bot] = (sym, risk, npct, s)
    print(f"{bot:<7}{sym:<12}{risk:>9.4%}{stop:>10.5f}{ov:>9.2f}{opct:>9.4%}{opct/risk:>7.2f}"
          f"{nv:>9.2f}{npct:>9.4%}{npct/risk:>7.2f}")

print("\n--- CORE INVARIANT ---")
for bot, (sym, risk, npct, s) in after.items():
    ck(f"A {bot} realised <= intended", npct <= risk + 1e-12, f"{npct:.6%} > {risk:.6%}")

ck("B BOT_D can no longer exceed intended risk", after["BOT_D"][2] <= after["BOT_D"][1] + 1e-12)
ck("C BOT_H can no longer exceed intended risk", after["BOT_H"][2] <= after["BOT_H"][1] + 1e-12)
_, r_d, p_d, _ = ("", *after["BOT_D"][1:3], None)
print(f"      BOT_D was 1.13x -> now {after['BOT_D'][2]/after['BOT_D'][1]:.2f}x; "
      f"BOT_H was 1.13x -> now {after['BOT_H'][2]/after['BOT_H'][1]:.2f}x")

print("\n--- GROUP CAP: the C+D+E combination that breached 0.15% by rounding ---")
grp = sum(after[b][2] for b in ("BOT_C", "BOT_D", "BOT_E"))
old_grp = sum(old_size(EQ, after[b][1], dict(CASES_D := {c[0]: c[3] for c in CASES})[b],
                       info(after[b][0]))[1] for b in ("BOT_C", "BOT_D", "BOT_E"))
print(f"      intended 0.1500%   RC1 realised {old_grp:.4%}   TASK-0006 realised {grp:.4%}   cap {D.GROUP_CAP:.4%}")
ck("D C+D+E breached the cap before the patch", old_grp > D.GROUP_CAP, f"{old_grp:.4%}")
ck("E C+D+E is inside the cap after the patch", grp <= D.GROUP_CAP + 1e-12, f"{grp:.4%}")

print("\n--- GLOBAL CAP operates on realised exposure ---")
tot = sum(v[2] for v in after.values())
ck("F all eight simultaneously stay inside the 0.75% total cap", tot <= D.TOTAL_CAP + 1e-12, f"{tot:.4%}")
print(f"      realised total {tot:.4%} vs cap {D.TOTAL_CAP:.4%}")
gate_ok, why = CC.exposure_gate({"BREAKOUT": D.GROUP_CAP - 0.00001}, D.GROUP_CAP - 0.00001,
                                "BREAKOUT", after["BOT_H"][2])
ck("G the pre-send gate spends realised risk and refuses the overflow", not gate_ok, why)

print("\n--- MINIMUM-LOT SKIP: never silently up-size ---")
tiny = types.SimpleNamespace(volume_min=1.0, volume_step=1.0, volume_max=100.0,
                             trade_tick_value=1.0, trade_tick_size=0.01, trade_contract_size=100.0)
s = CC.size_position(EQ, 0.0005, 14.10, tiny, 4375.0)
ck("H a minimum lot whose own risk exceeds the budget is SKIPPED", s["ok"] is False, s)
ck("I the skip names the risk that minimum lot would have carried", "above the requested" in s["reason"], s["reason"])
ck("J no volume is returned when skipping", s["volume"] is None)
s2 = CC.size_position(EQ, 0.0005, 14.10, info("XAUUSD"), 4375.0)
ck("K a sizeable case still returns a volume", s2["ok"] and s2["volume"] > 0)

print("\n--- volume_max still honoured ---")
capped = types.SimpleNamespace(volume_min=0.01, volume_step=0.01, volume_max=0.02,
                               trade_tick_value=1.0, trade_tick_size=0.01, trade_contract_size=100.0)
s3 = CC.size_position(EQ, 0.0100, 14.10, capped, 4375.0)
ck("L volume never exceeds volume_max", s3["volume"] <= 0.02 + 1e-12, s3)

print("\n--- LEGACY LEDGER ROWS are never read as carrying LESS risk ---")
legacy_bare = {"risk_pct": 0.0005}
ck("M a bare legacy row falls back to its intended figure",
   CC.realised_risk_of(legacy_bare) == 0.0005)
legacy_full = {"risk_pct": 0.0005, "volume": 0.04, "entry": 4375.0, "stop": 4360.9,
               "account_equity": EQ}
proven = CC.realised_risk_of(legacy_full, info=info("XAUUSD"))
ck("N a reconstructable legacy row is recomputed from volume x stop x tick economics",
   abs(proven - (0.04 * 14.1 * 100 / EQ)) < 1e-9, proven)
ck("O the reconstruction is LARGER than the intended figure it replaces", proven > 0.0005, proven)
ck("P realised is preferred whenever the row carries it",
   CC.realised_risk_of({"risk_pct": 0.0005, "realised_risk_pct": 0.0004}) == 0.0004)

print("\n--- R normalises on risk actually committed ---")
import inspect
src = inspect.getsource(CC.reconcile)
ck("Q reconcile() computes risk_money via realised_risk_of", "realised_risk_of(r)" in src)
ck("R reconcile() no longer reads r['risk_pct'] directly", 'r["risk_pct"]' not in src)

print("\n--- untouched subsystems ---")
full = open("challenge_controller.py", encoding="utf-8").read()
ck("S broker SL/TP still never modified", "TRADE_ACTION_SLTP" not in full)
ck("T stop_geometry unchanged", "MIN_STOP_SPREAD_MULT = 30.0" in full and "MIN_STOP_ATR_FRAC = 0.15" in full)
ck("U risk targets unchanged", "RISK_EXPERIMENTAL = 0.0010" in full and "RISK_ESTABLISHED = 0.0025" in full)
ck("V caps unchanged", D.GROUP_CAP == 0.0015 and D.TOTAL_CAP == 0.0075)
ck("W clock gate and per-symbol gate still present",
   "MS.clock_state(mt5)" in full and "MS.symbol_feed_fresh(mt5, bot.symbol)" in full)
import ast as _ast
_fn = [n for n in _ast.walk(_ast.parse(inspect.getsource(CC.size_position).lstrip()))
       if isinstance(n, _ast.FunctionDef)][0]
_floors = [n for n in _ast.walk(_fn) if isinstance(n, _ast.Call)
           and isinstance(n.func, _ast.Attribute) and n.func.attr == "floor"]
_rounds = [n for n in _ast.walk(_fn) if isinstance(n, _ast.Call)
           and isinstance(n.func, _ast.Name) and n.func.id == "round"]
ck("X volume quantisation uses math.floor", len(_floors) >= 1, len(_floors))
ck("Y every round() in size_position is 2-arg float cleanup, never to-nearest-step",
   all(len(r.args) == 2 for r in _rounds), [len(r.args) for r in _rounds])
_scaled = [r for r in _rounds if len(r.args) == 1]
ck("Z no to-nearest-step rounding survives anywhere in sizing", not _scaled, _scaled)

print("\n" + ("ALL REALISED-RISK TESTS PASSED" if not FAILED
              else f"FAILURES ({len(FAILED)}): " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
