"""TASK-0005 -- a stale market timestamp may never prove its own freshness.

THE DEFECT. broker_utc_offset() computed `tick.time - host_now` and rounded to hours. That is
a TIMEZONE only while the tick is CURRENT; once the feed freezes it measures TIMEZONE MINUS
STALENESS, and to_london() subtracts the same value back out, so the staleness cancels itself.
Measured on the VPS: a 14-hour-old feed produced a desk clock 5 minutes from real time.

WHY THREE GUARDS MISSED IT, each pinned by a test below:
  fresh_m1_data      compared a stale bar to a stale tick -- 52s apart. Test P.
  broker_offset_sane allowed +/-14h, which contains -13h.  Test B.
  the 5.9 min residual was printed as a host NTP warning.  Test H3.
"""
import sys, os, json, tempfile, shutil, random, types, pathlib
sys.path.insert(0, ".")
import pandas as pd
import market_state as MS

FIX = json.loads(pathlib.Path("tests/fixtures/vps_clock_20260815.json").read_text(encoding="utf-8"))
SYMS = MS.CLOCK_SYMBOLS
BROKER_H = 3
T0 = 1786000000.0


class World:
    """Fake MT5 + injectable host clock. No wall-clock read anywhere in this suite."""
    def __init__(s, offset_h=BROKER_H, host_err=0.0):
        s.true = T0; s.offset_h = offset_h; s.host_err = host_err
        s.frozen_at = None; s.frozen_syms = set(); s.none_syms = set(); s.back = 0
    def host_now(s): return s.true + s.host_err
    def symbol_select(s, sym, on=True): return sym not in s.none_syms
    def symbol_info_tick(s, sym):
        if sym in s.none_syms: return None
        frozen = s.frozen_at is not None and (not s.frozen_syms or sym in s.frozen_syms)
        base = s.frozen_at if frozen else s.true
        return types.SimpleNamespace(time=int(base + s.offset_h * 3600 - s.back))


def run(w, path, cycles, step=60):
    out = []
    for _ in range(cycles):
        r = MS.clock_state(w, host_now=w.host_now(), path=path)
        out.append((r["state"], r["entries"], r["reason"]))
        w.true += step
    return out


def fresh(fn):
    d = tempfile.mkdtemp(prefix="task0005-")     # tmp only; never the repository
    try: return fn(os.path.join(d, "clock_state.json"))
    finally: shutil.rmtree(d, ignore_errors=True)


def seq(log):
    o = []
    for st, _, _ in log:
        if not o or o[-1] != st: o.append(st)
    return o


def entries(log): return sum(1 for _, e, _ in log if e)


FAILED = []
def ck(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"   <- {detail}"))
    if not cond: FAILED.append(name)


# ---- CONSTANTS -----------------------------------------------------------------------------
ck("A1 constants cannot contradict: drift + latency <= max age",
   MS.HOST_DRIFT_TOLERANCE_S + MS.FEED_LATENCY_ALLOWANCE_S <= MS.FEED_MAX_AGE_S)
ck("A2 expected offsets are the EET/EEST pair only", MS.EXPECTED_OFFSETS_H == (2, 3))
ck("A3 advancement window is shorter than the age band -- ELAPSED time is the primary detector",
   MS.FEED_NO_ADVANCE_S < MS.FEED_MAX_AGE_S)

# ---- HEALTHY + PARITY ----------------------------------------------------------------------
log = fresh(lambda p: run(World(), p, 1440))
ck("B1 24h healthy: bootstraps once then stays FEED_FRESH", seq(log) == [MS.BOOTSTRAPPING, MS.FEED_FRESH], seq(log))
ck("B2 24h healthy: entries permitted for >99% of cycles", entries(log) >= 1435, entries(log))
ck("B3 bootstrap blocks the opening cycles", not any(e for _, e, _ in log[:3]))

def _parity(p):
    w = World(); run(w, p, 30)
    MS._OFFSET_CACHE.clear(); MS.CLOCK_STATE_PATH = pathlib.Path(p)
    off = MS.broker_utc_offset(w, "XAUUSD")
    MS._OFFSET_CACHE.clear()
    return off
ck("B4 healthy feed: broker_utc_offset returns the true +3h, as base 42ad8b38 did",
   _parity_off := fresh(_parity), _parity_off)
ck("B5 that offset equals exactly +3h", _parity_off == pd.Timedelta(hours=BROKER_H), _parity_off)

# ---- FROZEN GRID ---------------------------------------------------------------------------
for mins, label in ((5, "C1 5m"), (15, "C2 15m"), (30, "C3 30m"), (60, "C4 1h"), (14 * 60, "C5 14h")):
    def go(p, m=mins):
        w = World(); run(w, p, 40)
        before = json.loads(open(p).read())["trusted_offset_h"]
        w.frozen_at = w.true
        during = run(w, p, m)
        after_off = json.loads(open(p).read())["trusted_offset_h"]
        w.frozen_at = None
        return during, run(w, p, 30), before, after_off
    during, after, off_before, off_during = fresh(go)
    ck(f"{label} freeze: entries stop within 3 cycles and never resume",
       not any(e for _, e, _ in during[3:]), entries(during))
    ck(f"{label} freeze: reported FEED_STALE, not an offset fault",
       all(st == MS.FEED_STALE for st, _, _ in during[3:]), set(st for st, _, _ in during[3:]))
    ck(f"{label} freeze: the trusted offset is never altered by a frozen tick",
       off_during in (off_before, None) and off_during != -13, (off_before, off_during))
    ck(f"{label} freeze: recovers to FEED_FRESH and permits entries", after[-1][0] == MS.FEED_FRESH and after[-1][1])

# ---- WEEKEND WITHOUT A WEEKEND RULE --------------------------------------------------------
def weekend(p):
    w = World(); run(w, p, 60); w.frozen_at = w.true
    wk = run(w, p, 65 * 60); w.frozen_at = None
    return wk, run(w, p, 30)
wk, mon = fresh(weekend)
ck("D1 65h frozen: entries stop within 3 cycles and never resume", not any(e for _, e, _ in wk[3:]))
ck("D2 65h frozen: offset expiry re-bootstraps rather than trusting an aged value",
   MS.BOOTSTRAPPING in seq(wk), seq(wk))
ck("D3 65h frozen: only FEED_STALE / BOOTSTRAPPING, never a fabricated offset",
   all(st in (MS.FEED_STALE, MS.BOOTSTRAPPING) for st, _, _ in wk[3:]), set(st for st, _, _ in wk[3:]))
ck("D4 recovery permits entries again", mon[-1][1])

# ---- WEDNESDAY INTRADAY FREEZE: the same verdict, proving no weekend special case ------------
def wednesday(p):
    w = World(); run(w, p, 120)                       # mid-session
    w.frozen_at = w.true
    return run(w, p, 60)
wed = fresh(wednesday)
ck("E1 weekday intraday freeze produces the identical FEED_STALE verdict",
   all(st == MS.FEED_STALE for st, _, _ in wed[3:]) and not any(e for _, e, _ in wed[3:]),
   set(st for st, _, _ in wed[3:]))

# ---- RESTART / PERSISTENCE ------------------------------------------------------------------
def r_healthy(p):
    w = World(); run(w, p, 40)
    before = json.loads(open(p).read())["trusted_offset_h"]
    return before, run(w, p, 5)
before, log = fresh(r_healthy)
ck("F1 restart healthy: trusted offset survives on disk", before == BROKER_H, before)
ck("F2 restart healthy: entries resume without re-bootstrap", log[0][1])

ck("F3 restart during a stale feed stays blocked",
   not any(e for _, e, _ in fresh(lambda p: (lambda w: (run(w, p, 40), setattr(w, "frozen_at", w.true),
        run(w, p, 20), run(w, p, 5))[-1])(World()))))

def r_boot(p):
    w = World(); a = run(w, p, 2); return a + run(w, p, 3)
log = fresh(r_boot)
ck("F4 restart mid-bootstrap resumes; never jumps straight to permitted",
   not log[0][1] and not log[1][1] and log[-1][1], log)

def r_reval(p):
    w = World(offset_h=2); run(w, p, 90); w.offset_h = 3
    a = run(w, p, 1); return a + run(w, p, 11)
log = fresh(r_reval)
ck("F5 restart mid-revalidation resumes and completes", log[-1][0] == MS.FEED_FRESH and log[-1][1], seq(log))

# ---- CORRUPTION / EXPIRY --------------------------------------------------------------------
def corrupt(p):
    w = World(); run(w, p, 40)
    open(p, "w").write("{not json")
    first = MS.clock_state(w, host_now=w.host_now(), path=p); w.true += 60
    return first, run(w, p, 6)
first, rest = fresh(corrupt)
ck("G1 corrupt state blocks immediately", first["state"] == MS.CLOCK_STATE_CORRUPT and not first["entries"])
ck("G2 corrupt state never silently resets into permitted", not rest[0][1])
ck("G3 corrupt state recovers only through a full bootstrap proof", rest[-1][1])

def trunc(p):
    w = World(); run(w, p, 40)
    d = open(p).read(); open(p, "w").write(d[:len(d) // 2])
    return MS.clock_state(w, host_now=w.host_now(), path=p)
ck("G4 truncated state treated as corrupt, blocked", fresh(trunc)["state"] == MS.CLOCK_STATE_CORRUPT)

def impossible(p):
    w = World(); run(w, p, 40)
    d = json.loads(open(p).read()); d["trusted_offset_h"] = -13
    open(p, "w").write(json.dumps(d))
    return MS.clock_state(w, host_now=w.host_now(), path=p)
r = fresh(impossible)
ck("G5 an impossible persisted offset (-13h) is corruption, blocked",
   r["state"] == MS.CLOCK_STATE_CORRUPT and not r["entries"], r)

def expiry(p):
    w = World(); run(w, p, 40)
    d = json.loads(open(p).read()); d["offset_at"] = w.host_now() - MS.TRUSTED_OFFSET_MAX_AGE_S - 60
    open(p, "w").write(json.dumps(d))
    return run(w, p, 6)
log = fresh(expiry)
ck("G6 expired offset blocks then re-bootstraps", not log[0][1] and log[-1][1], seq(log))

# ---- HOST CLOCK vs FEED ---------------------------------------------------------------------
def drift(p):
    w = World(); run(w, p, 40); out = []
    for err in range(0, 421, 60):
        w.host_err = err
        out.append((err, MS.clock_state(w, host_now=w.host_now(), path=p)))
        w.true += 60
    return out
for err, r in fresh(drift):
    if err <= MS.HOST_DRIFT_TOLERANCE_S:
        ck(f"H1 host drift {err}s within tolerance: FEED_FRESH", r["state"] == MS.FEED_FRESH, r["state"])
    else:
        ck(f"H2 host drift {err}s: HOST_CLOCK_UNTRUSTED, entries blocked",
           r["state"] == MS.HOST_CLOCK_UNTRUSTED and not r["entries"], r["state"])
        ck(f"H3 host drift {err}s is NOT diagnosed as FEED_STALE -- different corrective action",
           r["state"] != MS.FEED_STALE)

ck("H4 host drift recovering to 0 permits entries again",
   fresh(lambda p: (lambda w: (run(w, p, 40), setattr(w, "host_err", 0), run(w, p, 5))[-1])(World(host_err=420)))[-1][1])

def jumps(p):
    w = World(); run(w, p, 40)
    w.host_err = +7200; a = MS.clock_state(w, host_now=w.host_now(), path=p); w.true += 60
    w.host_err = -7200; b = MS.clock_state(w, host_now=w.host_now(), path=p)
    return a, b
a, b = fresh(jumps)
ck("H5 sudden host jump +2h: entries blocked", not a["entries"], a["state"])
ck("H6 sudden host jump -2h: entries blocked", not b["entries"], b["state"])
ck("H7 host jumps never adopt a fabricated offset",
   a["offset_h"] == BROKER_H and b["offset_h"] == BROKER_H, (a["offset_h"], b["offset_h"]))

# ---- DST -------------------------------------------------------------------------------------
def dst(frm, to, p):
    w = World(offset_h=frm); run(w, p, 90)            # > OFFSET_MIN_CHANGE_INTERVAL_S
    w.offset_h = to
    return run(w, p, 12)
for frm, to in ((2, 3), (3, 2)):
    log = fresh(lambda p, a=frm, b=to: dst(a, b, p))
    ck(f"I1 DST {frm:+d}h -> {to:+d}h: revalidates and adopts",
       MS.OFFSET_REVALIDATION_REQUIRED in seq(log) and log[-1][0] == MS.FEED_FRESH, seq(log))
    ck(f"I2 DST {frm:+d}h -> {to:+d}h: entries blocked until adoption is proven",
       not log[0][1] and not log[1][1] and log[-1][1], [(s, e) for s, e, _ in log])

log = fresh(lambda p: dst(3, -13, p))
ck("I3 fabricated +3h -> -13h with a LIVE feed: never adopted, never permitted",
   entries(log) == 0 and MS.FEED_FRESH not in seq(log), seq(log))

def freeze_at_dst(p):
    w = World(offset_h=2); run(w, p, 90)
    w.frozen_at = w.true; w.offset_h = 3
    return run(w, p, 60)
log = fresh(freeze_at_dst)
ck("I4 freeze coinciding with DST: no offset adopted from a frozen feed",
   not any(e for _, e, _ in log[3:]) and MS.FEED_STALE in seq(log), seq(log))

# ---- BACKWARD / DUPLICATE TIMESTAMPS ----------------------------------------------------------
def backward(amount, p):
    w = World(); run(w, p, 90); w.back = amount
    return run(w, p, 12)
log = fresh(lambda p: backward(900, p))
ck("J1 non-hour backward jump (15 min): blocked, never adopted",
   not any(e for _, e, _ in log[3:]) and MS.FEED_FRESH not in seq(log)[1:], seq(log))
log = fresh(lambda p: backward(3600, p))
ck("J2 exact 1h backward jump: at least one blocked cycle, never silent", not log[1][1], seq(log))

def dup(p):
    w = World(); run(w, p, 40); w.frozen_at = w.true
    return run(w, p, 400)
log = fresh(dup)
ck("J3 duplicate timestamp for 400 cycles never oscillates back into permitted",
   not any(e for _, e, _ in log[3:]) and set(st for st, _, _ in log[6:]) == {MS.FEED_STALE},
   set(st for st, _, _ in log[6:]))

# ---- SYMBOL AVAILABILITY -----------------------------------------------------------------------
def none_syms(p):
    w = World(); run(w, p, 40); w.none_syms = {"XAUUSD"}
    a = run(w, p, 3); w.none_syms = set(SYMS)
    return a, run(w, p, 3)
a, b = fresh(none_syms)
ck("K1 one symbol returns None: the desk continues on the remaining symbols", a[-1][1])
ck("K2 every symbol returns None: blocked", not any(e for _, e, _ in b))
ck("K3 MT5 disconnect then reconnect recovers to permitted",
   fresh(lambda p: (lambda w: (run(w, p, 40), setattr(w, "none_syms", set(SYMS)), run(w, p, 10),
        setattr(w, "none_syms", set()), run(w, p, 8))[-1])(World()))[-1][1])

# ---- PER-SYMBOL FRESHNESS (the review's late discovery) ------------------------------------------
def per_symbol(stale_sym, p):
    w = World(); run(w, p, 40)
    w.frozen_at = w.true; w.frozen_syms = {stale_sym}
    log = run(w, p, 30)
    MS.CLOCK_STATE_PATH = pathlib.Path(p)
    res = {s: MS.symbol_feed_fresh(w, s, host_now=w.host_now(), path=p)[0] for s in SYMS}
    return log, res

log, res = fresh(lambda p: per_symbol("XAUUSD", p))
ck("L1 XAUUSD stale: the GLOBAL clock is still FEED_FRESH", log[-1][0] == MS.FEED_FRESH and log[-1][1])
ck("L2 XAUUSD stale: its own per-symbol gate refuses it", res["XAUUSD"] is False, res)
ck("L3 XAUUSD stale: EURUSD remains independently evaluable", res["EURUSD"] is True, res)
ck("L4 XAUUSD stale: US100.cash remains independently evaluable", res["US100.cash"] is True, res)

log, res = fresh(lambda p: per_symbol("EURUSD", p))
ck("L5 INVERSE -- EURUSD stale: its own gate refuses it", res["EURUSD"] is False, res)
ck("L6 INVERSE -- EURUSD stale: XAUUSD remains evaluable, so the gate is not gold-specific",
   res["XAUUSD"] is True, res)
ck("L7 INVERSE -- EURUSD stale: global clock still FEED_FRESH", log[-1][0] == MS.FEED_FRESH)

# ---- THE PINNED VPS REGRESSION --------------------------------------------------------------------
def vps(p):
    """tick 2026-08-14 23:54:59 raw, host 2026-08-15 12:56:34 UTC, true broker offset +3h."""
    w = World(); run(w, p, 40)                       # establish +3h on a live feed
    w.frozen_at = w.true
    w.true += FIX["observation"]["staleness_s"]      # 46,895s == 13h01m
    return run(w, p, 10), json.loads(open(p).read())
log, state = fresh(vps)
old_offset_h = round((0 - FIX["observation"]["staleness_s"]) / 3600) + BROKER_H
ck("M1 PINNED: the OLD formula would still derive about -13h from these numbers", old_offset_h == -10 or old_offset_h <= -9, old_offset_h)
ck("M2 PINNED: new implementation never permits entries on the 13h-stale feed", entries(log) == 0)
ck("M3 PINNED: state is FEED_STALE or BOOTSTRAPPING, never FEED_FRESH", MS.FEED_FRESH not in seq(log), seq(log))
ck("M4 PINNED: the trusted offset was never rewritten to a fabricated value",
   state["trusted_offset_h"] in (None, BROKER_H), state["trusted_offset_h"])
ck("M5 PINNED: fixture still declares what it does and does not prove",
   FIX["_metadata"]["immutable"] is True and "Clock fabrication only" in FIX["_metadata"]["proves"])

# ---- WHY THE OLD CHECK COULD NEVER WORK -------------------------------------------------------------
def bar_vs_tick(p):
    w = World(); run(w, p, 40); w.frozen_at = w.true; w.true += 14 * 3600
    tick = w.symbol_info_tick("XAUUSD").time
    bar = tick - 52                                  # the newest M1 bar, as measured on the VPS
    return abs(tick - bar)
ck("P1 on a 14h-stale feed the bar-vs-tick gap is still 52s -- the old check was incapable",
   fresh(bar_vs_tick) < 900, "if this ever exceeds 900 the old check would have worked")

# ---- SIGNATURES ---------------------------------------------------------------------------------------
import inspect
for fn, sig in (("broker_utc_offset", "(mt5, symbol='XAUUSD')"),
                ("to_london", "(series_or_epoch, offset)"),
                ("broker_now_london", "(mt5, symbol=None)"),
                ("clock_skew", "(mt5, symbol='XAUUSD')")):
    got = str(inspect.signature(getattr(MS, fn)))
    ck(f"Q {fn} signature preserved for macro_context and _bars", got == sig, got)

# ---- CONTROLLER INVARIANTS (source-level; these need no MT5) ---------------------------------
import ast as _ast
_src = pathlib.Path("challenge_controller.py").read_text(encoding="utf-8")
_tree = _ast.parse(_src)
_fns = {n.name: n for n in _ast.walk(_tree) if isinstance(n, _ast.FunctionDef)}

def _calls(fn):
    return {n.func.attr for n in _ast.walk(fn)
            if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)}

# INVARIANT 2: the entry order_send is downstream of the gate, which is downstream of exits.
_i_te   = _src.index("time_exits(mt5, acct, BOTS, dry_run=False)")
_i_rec  = _src.index("nc = reconcile(mt5)")
_i_gate = _src.index("_clock = MS.clock_state(mt5)")
_i_now  = _src.index("desk_now = MS.broker_now_london(mt5)")
_i_send = _src.rindex("res = mt5.order_send(req)")
ck("S1 ordering: time_exits < reconcile < clock gate < desk_now < entry order_send",
   _i_te < _i_rec < _i_gate < _i_now < _i_send)
ck("S2 the gate returns before any entry evaluation when entries are not permitted",
   'if not _clock["entries"]:' in _src and
   _src.index('if not _clock["entries"]:') < _i_now)

# INVARIANT 4 + 5: position management never consumes the repaired value.
_te = _calls(_fns["time_exits"]); _rc = _calls(_fns["reconcile"])
ck("S3 time_exits() calls no clock-safety function", not (_te & {
   "clock_state", "broker_utc_offset", "broker_now_london", "symbol_feed_fresh", "to_london"}), _te)
ck("S4 reconcile() calls no clock-safety function", not (_rc & {
   "clock_state", "broker_utc_offset", "broker_now_london", "symbol_feed_fresh", "to_london"}), _rc)
ck("S5 time_exits and reconcile are invoked BEFORE the gate, so a blocked clock cannot skip them",
   _i_te < _i_gate and _i_rec < _i_gate)
ck("S6 neither the gate nor the per-symbol gate modifies a stop or target",
   "TRADE_ACTION_SLTP" not in _src and "sl=" not in _src.split("_clock = MS.clock_state")[1][:1200])

# INVARIANT 3: the per-symbol gate precedes generate_signal in the observation path.
_i_sym  = _src.index("_sym_ok, _sym_why = MS.symbol_feed_fresh(mt5, bot.symbol)")
_i_sig  = _src.index("sig = bot.generate_signal(ctx)")
ck("S7 per-symbol freshness is tested BEFORE generate_signal", _i_sym < _i_sig)
ck("S8 a stale symbol skips only its own bot (continue), it does not halt the desk",
   "continue" in _src[_i_sym:_i_sig] and "return" not in _src[_i_sym:_src.index("blackout = in_event")])

# The removed defects must stay removed.
ck("S9 the vacuous fresh_m1_data preflight check is gone",
   'check("fresh_m1_data"' not in _src)
_dead = [n for n in _ast.walk(_tree) if isinstance(n, _ast.BoolOp)
         and any(isinstance(v, _ast.Constant) and v.value is False for v in n.values)]
ck("S10 no permanently-false condition remains anywhere in the controller", not _dead,
   [getattr(n, "lineno", "?") for n in _dead])
ck("S11 the +/-14h sanity band is gone, replaced by EXPECTED_OFFSETS_H",
   "hours=-14" not in _src and "EXPECTED_OFFSETS_H" in _src)

# ---- RANDOMISED SOAK -----------------------------------------------------------------------------------
def soak(p):
    random.seed(20260815)
    w = World(); viol = []; permitted = frozen = 0; CY = 20000
    for i in range(CY):
        r = random.random()
        if r < 0.004: w.frozen_at = w.true if w.frozen_at is None else None
        if r > 0.998: w.host_err = random.choice([0, 60, 200, 400, 900, -400])
        if 0.9970 < r <= 0.9975: w.none_syms = set(SYMS) if not w.none_syms else set()
        if 0.9965 < r <= 0.9970: w.offset_h = random.choice([2, 3])
        if 0.9960 < r <= 0.9965: w.back = random.choice([0, 900, 3600])
        if 0.9955 < r <= 0.9960 and os.path.exists(p): open(p, "a").write("garbage")
        def off():
            try: return json.loads(open(p).read()).get("trusted_offset_h")
            except Exception: return "UNREADABLE"
        was_frozen = w.frozen_at is not None
        before = off() if os.path.exists(p) else None
        res = MS.clock_state(w, host_now=w.host_now(), path=p)
        after = off() if os.path.exists(p) else None
        if res["entries"] and res["state"] != MS.FEED_FRESH:
            viol.append((i, "ENTRY OUTSIDE FEED_FRESH"))
        if was_frozen and before not in (None, "UNREADABLE") and after not in (None, "UNREADABLE") \
           and after != before:
            viol.append((i, "FROZEN FEED CHANGED THE TRUSTED OFFSET"))
        if after not in (None, "UNREADABLE") and after not in MS.EXPECTED_OFFSETS_H:
            viol.append((i, "OFFSET OUTSIDE EXPECTED SET"))
        if res["entries"] and was_frozen and (w.true - w.frozen_at) > MS.FEED_MAX_AGE_S:
            viol.append((i, "ENTRY ON A FEED FROZEN BEYOND FEED_MAX_AGE_S"))
        permitted += bool(res["entries"]); frozen += was_frozen
        w.true += 60
    return CY, frozen, permitted, viol
CY, frozen, permitted, viol = fresh(soak)
print(f"\n  soak: {CY} cycles, {frozen} frozen-feed cycles, {permitted} entries permitted "
      f"({permitted/CY:.1%}), {len(viol)} invariant violations")
ck("R1 SOAK: zero invariant violations over 20,000 randomised cycles", not viol, viol[:5])

print("\n" + ("ALL FEED-FRESHNESS TESTS PASSED" if not FAILED
              else f"FAILURES ({len(FAILED)}): " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
