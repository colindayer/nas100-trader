"""The script must be able to START ITSELF.

On 2026-08-19 a botched mechanical reindent in TASK-0007 deleted the last four lines of
challenge_controller.py -- mt5.shutdown() and the `if __name__ == "__main__": main()` guard.
The module still imported, every in-process test still passed, and the deployed controller ran
every minute for nine minutes doing NOTHING: no cycle, no log line, no event, exit code 0.

Every other test in this suite imports the module and calls main() directly, so not one of
them could observe that the file had no way to begin. This one runs it the way Task Scheduler
does: as a subprocess, with no console, and checks that work actually happened.
"""
import os, sys, ast, shutil, tempfile, pathlib, subprocess
sys.path.insert(0, ".")

FAILED = []
def ck(n, c, d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}" + ("" if c else f"   <- {d}"))
    if not c: FAILED.append(n)

SRC = pathlib.Path("challenge_controller.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)

# ---- structural: the guard exists and calls main()
guards = [n for n in TREE.body if isinstance(n, ast.If)
          and ast.unparse(n.test).replace(" ", "").replace("'", '"') == '__name__=="__main__"']
ck("A the module has an `if __name__ == \"__main__\":` guard", len(guards) == 1, len(guards))
if guards:
    calls = [ast.unparse(s) for s in guards[0].body]
    ck("B the guard calls main()", calls == ["main()"], calls)
main_fn = [n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == "main"]
ck("C main() is defined", len(main_fn) == 1)
ck("D main() ends by shutting the broker connection down",
   main_fn and ast.unparse(main_fn[0].body[-1]) == "mt5.shutdown()",
   ast.unparse(main_fn[0].body[-1]) if main_fn else None)

# ---- behavioural: run it exactly as the scheduled task does
STUB = '''
import types, time
TIMEFRAME_D1=16408; TIMEFRAME_H4=16388; TIMEFRAME_H1=16385
TIMEFRAME_M15=15; TIMEFRAME_M5=5; TIMEFRAME_M1=1
TRADE_ACTION_DEAL=1; TRADE_RETCODE_DONE=10009
ORDER_TYPE_BUY=0; ORDER_TYPE_SELL=1; ORDER_TIME_GTC=0; ORDER_FILLING_IOC=1
def initialize(*a,**k): return True
def shutdown(): pass
def last_error(): return (0,"ok")
def account_info(): return types.SimpleNamespace(login=LOGIN,server=SERVER,trade_mode=0,
    equity=100000.0,balance=100000.0,currency="USD")
def terminal_info(): return types.SimpleNamespace(trade_allowed=True,connected=True)
def symbol_select(s,on=True): return True
def symbol_info_tick(s):
    return types.SimpleNamespace(time=int(time.time()+3*3600),bid=4000.0,ask=4000.5)
def symbol_info(s): return types.SimpleNamespace(volume_min=0.01,volume_step=0.01,
    volume_max=100.0,trade_tick_value=1.0,trade_tick_size=0.01,trade_contract_size=100.0)
def copy_rates_from_pos(s,tf,st,ct):
    import numpy as np
    sec={16408:86400,16388:14400,16385:3600,15:900,5:300,1:60}.get(tf,60)
    b=time.time()+3*3600
    return np.array([(b-(ct-i)*sec,4000.0,4002.0,3998.0,4000.5,100,2,0) for i in range(ct)],
        dtype=[("time","i8"),("open","f8"),("high","f8"),("low","f8"),("close","f8"),
               ("tick_volume","i8"),("spread","i4"),("real_volume","i8")])
def positions_get(**k): return []
def orders_get(**k): return []
def history_deals_get(*a,**k): return []
def order_send(r): return types.SimpleNamespace(retcode=10009,price=r["price"],order=1,deal=1,
    volume=r["volume"])
'''
ge = pathlib.Path("config/guardian.env").read_text(encoding="utf-8")
login = [l for l in ge.splitlines() if l.startswith("ACCOUNT_LOGIN")][0].split("=")[1].strip()
srv = [l for l in ge.splitlines() if l.startswith("ACCOUNT_SERVER_CONTAINS")][0].split("=")[1].strip()

work = tempfile.mkdtemp(prefix="entrypoint-")
try:
    for f in pathlib.Path(".").glob("*.py"): shutil.copy(f, work)
    shutil.copytree("config", os.path.join(work, "config"))
    stub = os.path.join(work, "_stub")
    os.makedirs(stub)
    pathlib.Path(stub, "MetaTrader5.py").write_text(
        f'LOGIN={login}\nSERVER="{srv}-Demo"\n' + STUB, encoding="utf-8")
    for d in ("data/logs", "data/challenge", "data/brain"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    env = {**os.environ, "PYTHONPATH": stub, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "challenge_controller.py", "--dry-run"],
                       cwd=work, env=env, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=180)
    logs = list(pathlib.Path(work, "data", "logs").glob("controller-*.log"))
    logtext = logs[0].read_text(encoding="utf-8", errors="replace") if logs else ""
    events = pathlib.Path(work, "data", "logs", "events.jsonl")
    evtext = events.read_text(encoding="utf-8") if events.exists() else ""

    ck("E the subprocess exits 0", r.returncode == 0, r.returncode)
    ck("F it PRODUCES OUTPUT -- the regression that shipped silently",
       len(r.stdout) > 200, f"{len(r.stdout)} bytes stdout, {len(r.stderr)} stderr")
    ck("G it writes a controller log file", bool(logs), "no controller-*.log created")
    ck("H the log contains a cycle header", "===== cycle" in logtext, logtext[:120])
    ck("I the log records the demo gate", "DEMO GATE OK" in logtext)
    ck("J it reaches preflight", "PREFLIGHT" in logtext, logtext[-200:])
    ck("K it emits structured events", evtext.count("\n") >= 1, evtext[:200])
    ck("L stdout and the log file agree",
       "===== cycle" in r.stdout and "===== cycle" in logtext)
finally:
    shutil.rmtree(work, ignore_errors=True)

print("\n" + ("ENTRY-POINT TESTS PASSED" if not FAILED
              else f"FAILURES ({len(FAILED)}): " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
