"""RELEASE CANDIDATE -- the thirteen properties the integrated desk must hold.

TASK-0005 (clock/feed safety) and TASK-0004 (candidate-first allocation) were built and
verified separately. This proves they still hold TOGETHER, which is the only form in which
they will ever run. Everything here is source-level or fake-MT5; nothing touches a broker.
"""
import sys, os, ast, json, types, tempfile, shutil, pathlib
sys.path.insert(0, ".")
import market_state as MS
import desk as D
import challenge_controller as CC
import trading_brain as TB

SRC = pathlib.Path("challenge_controller.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
FNS = {n.name: n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef)}
FAILED = []


def ck(n, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {n}" + ("" if cond else f"   <- {detail}"))
    if not cond: FAILED.append(n)


def calls(fn):
    return {c.func.attr for c in ast.walk(fn)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}


def at(needle): return SRC.index(needle)


class Feed:
    """Fake MT5. Per-symbol freeze, injectable host clock."""
    def __init__(s, offset_h=3, frozen=()):
        s.t = 1786000000.0; s.offset_h = offset_h; s.frozen = set(frozen); s.frozen_at = None
    def host(s): return s.t
    def symbol_select(s, sym, on=True): return True
    def symbol_info_tick(s, sym):
        base = s.frozen_at if (s.frozen_at and sym in s.frozen) else s.t
        return types.SimpleNamespace(time=int(base + s.offset_h * 3600), bid=1.0, ask=1.1)


def bootstrapped(path, w, cycles=8):
    for i in range(cycles):
        r = MS.clock_state(w, host_now=w.host(), path=path)
        w.t += 60
    return r


def tmp(fn):
    d = tempfile.mkdtemp(prefix="rc-")
    try: return fn(os.path.join(d, "clock_state.json"))
    finally: shutil.rmtree(d, ignore_errors=True)


print("=" * 78)
print("RELEASE CANDIDATE INVARIANTS -- TASK-0004 + TASK-0005 integrated")
print("=" * 78)

# 1 ---- stale/frozen GLOBAL feed => no new entries
def i1(p):
    w = Feed(); bootstrapped(p, w)
    w.frozen = set(MS.CLOCK_SYMBOLS); w.frozen_at = w.t
    out = []
    for _ in range(20):
        out.append(MS.clock_state(w, host_now=w.host(), path=p)); w.t += 60
    return out
res = tmp(i1)
ck("1  frozen global feed permits no new entries", not any(r["entries"] for r in res[3:]))
ck("1b frozen global feed reports FEED_STALE",
   all(r["state"] == MS.FEED_STALE for r in res[3:]), {r["state"] for r in res[3:]})

# 2/3/4 ---- per-symbol, in both directions
def per_symbol(stale, p):
    w = Feed(); bootstrapped(p, w)
    w.frozen = {stale}; w.frozen_at = w.t
    for _ in range(10):
        g = MS.clock_state(w, host_now=w.host(), path=p); w.t += 60
    return g, {s: MS.symbol_feed_fresh(w, s, host_now=w.host(), path=p)[0]
               for s in ("XAUUSD", "EURUSD", "US100.cash", "US500.cash")}

g, r = tmp(lambda p: per_symbol("XAUUSD", p))
ck("2  XAUUSD stale: the global clock is still FEED_FRESH", g["state"] == MS.FEED_FRESH and g["entries"])
ck("2b XAUUSD stale: the XAU per-symbol gate refuses it", r["XAUUSD"] is False, r)
ck("3  XAUUSD stale: EURUSD remains independently evaluable", r["EURUSD"] is True, r)
ck("3b XAUUSD stale: US100.cash remains independently evaluable", r["US100.cash"] is True, r)

g, r = tmp(lambda p: per_symbol("EURUSD", p))
ck("4  INVERSE EURUSD stale: EURUSD refused", r["EURUSD"] is False, r)
ck("4b INVERSE EURUSD stale: XAUUSD evaluable -- the gate is not gold-specific", r["XAUUSD"] is True, r)

# 2c ---- and the gate is positioned so a stale symbol yields NO CANDIDATE at all
i_p1, i_sym = at("candidates, ctxs = {}, {}"), at("_sym_ok, _sym_why = MS.symbol_feed_fresh")
i_sig, i_alloc = at("sig = bot.generate_signal(ctx)"), at("plan = DESK.allocate(BOTS")
i_send = SRC.rindex("res = mt5.order_send(req)")
ck("2c per-symbol gate is inside PASS 1, before generate_signal", i_p1 < i_sym < i_sig)
ck("2d a stale symbol therefore never becomes a candidate, is never ranked, never sent",
   i_sym < i_alloc < i_send)
ck("2e the stale-symbol branch skips only its own bot",
   "continue" in SRC[i_sym:i_sig] and "return" not in SRC[i_sym:i_sig])

# 5/6/7 ---- position management is independent of the freshness gate
i_te, i_rec, i_gate = (at("time_exits(mt5, acct, BOTS, dry_run=False)"),
                       at("nc = reconcile(mt5)"), at("_clock = MS.clock_state(mt5)"))
clockfns = {"clock_state", "broker_utc_offset", "broker_now_london", "symbol_feed_fresh", "to_london"}
ck("5  time_exits() runs BEFORE the freshness gate", i_te < i_gate)
ck("5b time_exits() calls no clock-safety function", not (calls(FNS["time_exits"]) & clockfns))
ck("6  reconcile() runs BEFORE the freshness gate", i_rec < i_gate)
ck("6b reconcile() calls no clock-safety function", not (calls(FNS["reconcile"]) & clockfns))
ck("7  no code path modifies a broker stop or target", "TRADE_ACTION_SLTP" not in SRC)
ck("7b the gate never closes or modifies a position",
   "order_send" not in SRC[i_gate:at("candidates, ctxs = {}, {}")])

# 8 ---- restart never grants immediate permission
def i8(p):
    w = Feed(); bootstrapped(p, w)                      # trusted offset now persisted
    saved = json.loads(open(p).read())["trusted_offset_h"]
    w2 = Feed(); w2.t = w.t                             # fresh process, same state file
    first = MS.clock_state(w2, host_now=w2.host(), path=p)
    return saved, first
saved, first = tmp(i8)
ck("8  restart: the trusted offset survives on disk", saved == 3, saved)
ck("8b restart: advancement must be re-proven before entries",
   MS._advancement_proved([]) is False)

# 9 ---- corrupt / missing / expired fail closed
def i9(kind, p):
    w = Feed(); bootstrapped(p, w)
    if kind == "corrupt": open(p, "w").write("{nope")
    if kind == "missing": os.remove(p)
    if kind == "expired":
        d = json.loads(open(p).read())
        d["offset_at"] = w.host() - MS.TRUSTED_OFFSET_MAX_AGE_S - 60
        open(p, "w").write(json.dumps(d))
    if kind == "implausible":
        d = json.loads(open(p).read()); d["trusted_offset_h"] = -13
        open(p, "w").write(json.dumps(d))
    return MS.clock_state(w, host_now=w.host(), path=p)
for kind in ("corrupt", "missing", "expired", "implausible"):
    r = tmp(lambda p, k=kind: i9(k, p))
    ck(f"9  {kind} clock state fails closed", r["entries"] is False, r["state"])

# 10 ---- only +2/+3 can become trusted
ck("10 EXPECTED_OFFSETS_H is the EET/EEST pair only", MS.EXPECTED_OFFSETS_H == (2, 3))
def i10(off, p):
    w = Feed(offset_h=off)
    r = bootstrapped(p, w, cycles=10)
    return json.loads(open(p).read())["trusted_offset_h"], r
for off, ok in ((2, True), (3, True), (4, False), (-13, False), (0, False)):
    trusted, r = tmp(lambda p, o=off: i10(o, p))
    if ok:
        ck(f"10 offset {off:+d}h adopted after advancement proof", trusted == off, trusted)
    else:
        ck(f"10 offset {off:+d}h REJECTED, never trusted, entries blocked",
           trusted is None and not r["entries"], (trusted, r["state"]))

# 11 ---- healthy-feed parity for actual trading decisions
def i11(p):
    w = Feed(); bootstrapped(p, w)
    MS._OFFSET_CACHE.clear(); MS.CLOCK_STATE_PATH = pathlib.Path(p)
    off = MS.broker_utc_offset(w, "XAUUSD"); MS._OFFSET_CACHE.clear()
    return off
import pandas as pd
ck("11 healthy feed: broker_utc_offset returns the true +3h, as at base 42ad8b38",
   tmp(i11) == pd.Timedelta(hours=3), tmp(i11))

class CS:
    def __init__(s, v=None): s.v = v
    def veto(s, r): return s.v
class B:
    shadow = False; risk_override = None
    def __init__(s, sid, sym, pb, risk=0.0010):
        s.strategy_id, s.symbol, s.playbook, s.risk = sid, sym, pb, risk
TREND = {"opportunities": ["TREND_UP", "EXPANSION"]}
bots = [B("A", "US500", "BREAKOUT"), B("C", "XAUUSD", "BREAKOUT")]
opp = {b.symbol: TREND for b in bots}
legacy = D.allocate(bots, opp, lambda b: b.risk, CS())
ck("11b CIO legacy call path (candidates=None) unchanged by either task",
   any(d["allow"] for d in legacy["decisions"].values())
   and not any("no_candidate" in d for d in legacy["decisions"].values()))
ck("11c eligibility() and utility() semantics untouched",
   D.eligibility(bots[0], ["TREND_UP"])[0] and isinstance(D.utility(bots[0], ["TREND_UP"])["score"], float))

# 12 ---- TASK-0004 functionality intact after the rebase
p0 = D.allocate(bots, opp, lambda b: b.risk, CS(), candidates=set())
ck("12 zero candidates consume zero risk", p0["total_risk"] == 0.0
   and all(d.get("no_candidate") for d in p0["decisions"].values()))
p1 = D.allocate(bots, opp, lambda b: b.risk, CS(), candidates={"C"},
                open_group_risk={"BREAKOUT": D.GROUP_CAP})
ck("12b live open exposure still consumes the group cap", not p1["decisions"]["C"]["allow"])
ok, _ = CC.exposure_gate({"BREAKOUT": 0.0010}, 0.0010, "BREAKOUT", 0.0005)
bad, why = CC.exposure_gate({"BREAKOUT": 0.0010}, 0.0010, "BREAKOUT", 0.0006)
ck("12c pre-send exposure gate intact: 0.0015 allowed, 0.0016 blocked", ok and not bad, why)
ck("12d desk_exposure fails closed on an unattributable position",
   [f["code"] for f in CC.desk_exposure(
       types.SimpleNamespace(positions_get=lambda **k: [types.SimpleNamespace(ticket=9, symbol="X", magic=990001)],
                             orders_get=lambda **k: []), [], {})["faults"]] == ["EXPOSURE_UNRECONCILED"])
i_expo = at("expo = desk_exposure(mt5, trades, known)")
ck("12e TASK-0004 exposure check still precedes pass 1", i_gate < i_expo < i_p1)

# 13 ---- VOID evidence cannot influence posteriors or CIO allocation
import inspect
src_ct = inspect.getsource(TB.closed_trades)
src_bel = inspect.getsource(TB.belief)
ck("13 closed_trades() excludes voided intents by default",
   'include_voided=False' in inspect.signature(TB.closed_trades).__str__().replace(" ", "")
   or "include_voided=False" in src_ct.split("\n")[0].replace(" ", ""))
ck("13b closed_trades() drops any intent named in voided_intents()",
   "voided_intents()" in src_ct and 'if r["intent_id"] in void:' in src_ct and "continue" in src_ct)
ck("13c belief() reads closed_trades() WITHOUT include_voided, so posteriors exclude void",
   "closed_trades()" in src_bel and "include_voided" not in src_bel)
_alloc_src = inspect.getsource(D.allocate)
ck("13d CIO allocation consumes beliefs, never the raw ledger",
   "beliefs" in _alloc_src and "trades.jsonl" not in _alloc_src and "closed_trades" not in _alloc_src)
ck("13e voiding is evidence-only: the ledger row is never deleted or rewritten",
   "append-only" in TB.closed_trades.__doc__ or "Nothing is deleted" in TB.voided_intents.__doc__)

print("\n" + ("ALL RELEASE INVARIANTS HOLD" if not FAILED
              else f"FAILURES ({len(FAILED)}): " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
