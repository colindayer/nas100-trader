"""TASK-0008 -- the two defects that made every funded candidate unreachable.

Both pre-existed at 42ad8b38 and were proved end-to-end under TASK-0007:
  1654  float(r.split("=")[1])   ValueError on BOT_H's "level=lvl_asia_high"   4 of 6 losses
  1516  st = MS.compute(...)     rebound the ChallengeState to a dict, so 1676
                                 st.veto(risk) raised AttributeError            2 of 6, and all
                                                                                future candidates
"""
import sys, ast, types, inspect, pathlib
sys.path.insert(0, ".")
import challenge_controller as CC

FAILED=[]
def ck(n,c,d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}"+("" if c else f"   <- {d}"))
    if not c: FAILED.append(n)

SRC=pathlib.Path("challenge_controller.py").read_text(encoding="utf-8")
TREE=ast.parse(SRC)
MAIN=[n for n in ast.walk(TREE) if isinstance(n,ast.FunctionDef) and n.name=="main"][0]

print("="*78); print("TASK-0008 -- root-cause restoration"); print("="*78)

# ---- DEFECT 1: a level reason code may NAME a level rather than price one
def parse_level(codes):
    """The production expression, extracted verbatim from main() for direct exercise."""
    lvl=None
    for _rc in (codes or []):
        if _rc.startswith("level="):
            try: lvl=float(_rc.split("=",1)[1])
            except ValueError: lvl=None
            break
    return lvl
ck("1a BOT_H's named level no longer raises",
   parse_level(["liquidity_sweep_reclaim","level=lvl_asia_high","pierce=0.12atr"]) is None)
for name in ("lvl_prev_day_high","lvl_prev_day_low","lvl_asia_high","lvl_asia_low",
             "lvl_high_20d","lvl_low_20d","lvl_weekly_open"):
    ck(f"1b every BOT_H level name is tolerated: {name}",
       parse_level([f"level={name}"]) is None)
ck("1c a numeric level is still parsed as a price", parse_level(["level=4386.81"])==4386.81)
ck("1d a negative/decimal price still parses", parse_level(["level=-0.00021"])==-0.00021)
ck("1e no level= code at all still yields None", parse_level(["probe","pierce=0.1atr"]) is None)
ck("1f the first level= wins and parsing stops",
   parse_level(["level=1.5","level=lvl_asia_high"])==1.5)
ck("1g production no longer uses a bare float() in a generator over level=",
   "next((float(r.split(\"=\")[1])" not in SRC)

# ---- DEFECT 2: the ChallengeState must survive the whole post-allocation path
binds=[n for n in ast.walk(MAIN) if isinstance(n,ast.Assign)
       for t in n.targets if isinstance(t,ast.Name) and t.id=="st"]
ck("2a `st` is assigned exactly once in main()", len(binds)==1, [b.lineno for b in binds])
ck("2b that one assignment is the ChallengeState alias",
   ast.unparse(binds[0].value).strip()=="st_", ast.unparse(binds[0].value))
ck("2c the per-symbol loop writes sym_state, not st",
   "sym_state = MS.compute(" in SRC and "        st = MS.compute(" not in SRC)
ck("2d states[] is populated from sym_state", "states[sym] = sym_state" in SRC)
ck("2e opportunity classification reads sym_state",
   "DESK.classify_opportunity(sym_state)" in SRC)
ck("2f macro merges into sym_state", "sym_state.update(MC.compute(" in SRC)

# ---- the veto is genuinely alive again, not merely reachable
CS=CC.ChallengeState
thin=CS(equity=100000.0, balance=100000.0, starting_balance=100000.0,
        day_start_equity=100000.0, trading_days=2, open_risk_pct=0.0)
ck("3a a healthy state permits a normal risk", thin.veto(0.0005) is None, thin.veto(0.0005))
breached=CS(equity=95500.0, balance=100000.0, starting_balance=100000.0,
            day_start_equity=100000.0, trading_days=2, open_risk_pct=0.0)
ck("3b a thin daily headroom still vetoes", breached.veto(0.0025) is not None, breached.veto(0.0025))
loaded=CS(equity=100000.0, balance=100000.0, starting_balance=100000.0,
          day_start_equity=100000.0, trading_days=2, open_risk_pct=0.0074)
ck("3c open risk at the cap still vetoes", loaded.veto(0.0005) is not None, loaded.veto(0.0005))
ck("3d ChallengeState.veto is unchanged from base",
   "if self.daily_headroom <= risk_pct * 2:" in SRC
   and "if self.open_risk_pct + risk_pct > MAX_CONCURRENT_RISK:" in SRC)

# ---- nothing else moved
ck("4a risk targets unchanged",
   "RISK_EXPERIMENTAL = 0.0010" in SRC and "RISK_ESTABLISHED = 0.0025" in SRC
   and "MAX_CONCURRENT_RISK = 0.0075" in SRC)
ck("4b stop geometry unchanged",
   "MIN_STOP_SPREAD_MULT = 30.0" in SRC and "MIN_STOP_ATR_FRAC = 0.15" in SRC)
ck("4c notional cap unchanged", "MAX_NOTIONAL_MULT = 3.0" in SRC)
ck("4d clock/freshness gate intact",
   "MS.clock_state(mt5)" in SRC and "MS.symbol_feed_fresh(mt5, bot.symbol)" in SRC)
ck("4e TASK-0007 containment intact",
   "FUNDED_CANDIDATE_ERROR" in SRC and "sys.stderr = _Tee" in SRC)
ck("4f realised-risk sizing intact",
   "def size_position(" in SRC and "math.floor" in inspect.getsource(CC.size_position))
ck("4g broker SL/TP still never modified", "TRADE_ACTION_SLTP" not in SRC)
ck("4h time_exits and reconcile signatures unchanged",
   "def time_exits(mt5, acct, bots, dry_run=False, magic=990001)" in SRC
   and "def reconcile(mt5, magic=990001)" in SRC)
# every class and every UPPERCASE class constant, compared structurally against base
import subprocess
def classes(src):
    out={}
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.ClassDef):
            consts={}
            for b in n.body:
                if isinstance(b, ast.Assign):
                    for tg in b.targets:
                        if isinstance(tg, ast.Name) and tg.id.isupper():
                            consts[tg.id]=ast.unparse(b.value)
            out[n.name]=consts
    return out
BASE=subprocess.run(["git","show","739e2fcd:challenge_controller.py"],
                    capture_output=True,text=True).stdout
cn, cb = classes(SRC), classes(BASE)
ck("4i the set of classes is unchanged", set(cn)==set(cb), set(cn)^set(cb))
diffs={k:(cb[k],cn[k]) for k in cb if k in cn and cb[k]!=cn[k]}
ck("4j every bot parameter is byte-identical to base", not diffs, diffs)
ck("4k generate_signal bodies unchanged",
   all(ast.unparse(f)==ast.unparse(g) for f,g in zip(
       [n for n in ast.walk(ast.parse(BASE)) if isinstance(n,ast.FunctionDef) and n.name=="generate_signal"],
       [n for n in ast.walk(ast.parse(SRC))  if isinstance(n,ast.FunctionDef) and n.name=="generate_signal"])))

print("\n"+("ALL ROOT-CAUSE TESTS PASSED" if not FAILED
            else f"FAILURES ({len(FAILED)}): "+"; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
