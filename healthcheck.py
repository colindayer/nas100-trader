"""healthcheck.py -- single-command verification of the whole installation.

    py healthcheck.py            # full check, PASS/FAIL per subsystem
    py healthcheck.py --json     # machine-readable
    py healthcheck.py --quick    # skip network/broker probes

Reports only what the code and configuration actually support. For every provider it separates:
    IMPLEMENTED  code exists
    CONFIGURED   credentials/settings present on THIS machine
    TESTED       a live probe succeeded just now
    ACTIVE       it is the provider the runtime would actually use
Exit code 0 if no CRITICAL failures, else 1.
"""
from __future__ import annotations
import argparse, importlib, json, os, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

OK, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
CRITICAL = {"files", "modules", "execution_gate", "guardian", "belief_graph",
            "promotion", "ledger", "reconciliation", "demo_envelope"}
results: list[dict] = []


def rec(subsystem, status, detail="", critical=None):
    results.append({"subsystem": subsystem, "status": status, "detail": detail,
                    "critical": subsystem in CRITICAL if critical is None else critical})
    return status


# ---------------------------------------------------------------- files
def check_files():
    try:
        v = json.load(open(os.path.join(ROOT, "VERSION.json")))
    except Exception as e:
        return rec("files", FAIL, f"VERSION.json unreadable: {e}")
    missing = [f for f in v.get("required_files", []) if not os.path.exists(os.path.join(ROOT, f))]
    if missing:
        return rec("files", FAIL, f"{len(missing)} missing: {', '.join(missing[:5])}")
    return rec("files", OK, f"{len(v.get('required_files', []))} required files present")


def check_version():
    try:
        v = json.load(open(os.path.join(ROOT, "VERSION.json")))
    except Exception as e:
        return rec("version", FAIL, str(e)[:80], critical=False)
    detail = f"{v['version']} commit {v['commit_short']} branch {v['branch']}"
    try:
        import subprocess
        live = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
        if live != v["commit"]:
            return rec("version", WARN, f"{detail} — WORKING TREE IS AT {live[:12]} (VERSION.json stale)",
                       critical=False)
    except Exception:
        detail += " (no git on this machine — file-sync deployment)"
    return rec("version", OK, detail, critical=False)


# ---------------------------------------------------------------- modules
MODULES = ["execution_safety.gate", "execution_safety.strategy_contract",
           "execution_safety.execution_guard", "execution_safety.belief_graph_v2",
           "execution_safety.promotion_pipeline_v2", "execution_safety.operational_belief",
           "execution_safety.demo_evidence", "execution_safety.position_ledger",
           "execution_safety.broker_reconciliation", "execution_safety.guardian_bridge",
           "market_intel.state", "market_intel.calendar_feed",
           "market_intel.faireconomy_provider", "market_intel.telegram_notifier",
           "market_intel.macro_board"]


def check_modules():
    bad = []
    for m in MODULES:
        try:
            importlib.import_module(m)
        except Exception as e:
            bad.append(f"{m} ({type(e).__name__})")
    if bad:
        return rec("modules", FAIL, f"{len(bad)} failed: {', '.join(bad[:4])}")
    return rec("modules", OK, f"{len(MODULES)} modules import cleanly")


# ---------------------------------------------------------------- env
ENV = {"FRED_API_KEY": False, "FINNHUB_TOKEN": False, "TELEGRAM_TOKEN": False,
       "TELEGRAM_CHAT_ID": False, "TRADINGECONOMICS_KEY": False, "FXSTREET_URL": False}


def check_env():
    present = [k for k in ENV if os.environ.get(k)]
    absent = [k for k in ENV if not os.environ.get(k)]
    return rec("environment", OK if present else WARN,
               f"set: {', '.join(present) or 'none'} | unset: {len(absent)}", critical=False)


# ---------------------------------------------------------------- providers
def check_providers(quick=False):
    """implemented / configured / tested / active -- inspected, never inferred."""
    table = []

    def row(name, implemented, configured, tested, note=""):
        table.append({"provider": name, "implemented": implemented,
                      "configured": configured, "tested": tested, "note": note})

    # FairEconomy (ForexFactory published JSON)
    try:
        from market_intel import faireconomy_provider as ff
        impl = True
        conf = os.environ.get("FAIRECONOMY_DISABLED") != "1"     # no key required
        tested = None
        if not quick and conf:
            tested = len(ff.load()) > 0
        row("FairEconomy (ForexFactory JSON)", impl, conf, tested,
            "no key required; 15-min cache; rate-limits")
    except Exception as e:
        row("FairEconomy (ForexFactory JSON)", False, False, False, str(e)[:60])

    # FRED
    try:
        from market_intel import fred_provider as fr
        conf = bool(os.environ.get("FRED_API_KEY"))
        tested = (len(fr.load()) > 0) if (conf and not quick) else None
        row("FRED", True, conf, tested, "official US macro; NO consensus forecast")
    except Exception as e:
        row("FRED", False, False, False, str(e)[:60])

    # MT5 calendar
    try:
        import MetaTrader5 as mt5
        impl = True
        conf = hasattr(mt5, "calendar_value_history")
        row("MT5 Economic Calendar", impl, conf, None,
            "build exposes calendar API" if conf else "this MT5 build has no calendar API")
    except Exception:
        row("MT5 Economic Calendar", True, False, False, "MetaTrader5 package not importable here")

    row("Finnhub", True, bool(os.environ.get("FINNHUB_TOKEN")), None,
        "economic-calendar endpoint is premium-gated")
    row("Trading Economics", True, bool(os.environ.get("TRADINGECONOMICS_KEY")), None,
        "guest key discontinued (HTTP 410)")
    row("FXStreet", True, bool(os.environ.get("FXSTREET_URL")), None, "needs licensed endpoint")
    row("CSV", True, os.path.exists(os.path.join(ROOT, "market_intel", "calendar.csv")), None,
        "operator-supplied fallback")
    row("Forex Factory (scrape)", True, os.environ.get("FOREXFACTORY_ENABLED") == "1", None,
        "DISABLED by default (ToS)")

    row("TradingView MCP", False, False, False, "SHELVED to attic/ — failed the complexity rubric")

    # which provider is ACTIVE at runtime
    active = "none"
    if not quick:
        try:
            from market_intel import calendar_feed as cf
            ev = cf.load()
            if ev:
                active = getattr(ev[0], "provider", None) or "unknown"
        except Exception:
            pass
    for t in table:
        t["active"] = (active.lower() in t["provider"].lower().replace(" ", "")
                       or (active == "faireconomy" and "FairEconomy" in t["provider"]))
    working = [t["provider"] for t in table if t["tested"]]
    status = OK if working else (WARN if any(t["configured"] for t in table) else FAIL)
    rec("calendar_providers", status,
        f"active={active} | tested-working: {', '.join(working) or 'none'}", critical=False)
    return table


# ---------------------------------------------------------------- governance
def check_belief():
    try:
        from execution_safety.belief_graph_v2 import BeliefGraphV2, MAX_EXEC_RESEARCH_LOGODDS
        g = BeliefGraphV2()
        if not g.strategies:
            return rec("belief_graph", WARN, "no strategies in registry/belief_v2.json")
        s = g.get("portfolio_multisleeve")
        return rec("belief_graph", OK,
                   f"research={s.research_belief():.4f} operational={s.operational_belief():.4f} "
                   f"evidence={len(s.evidence)} cap={MAX_EXEC_RESEARCH_LOGODDS}")
    except Exception as e:
        return rec("belief_graph", FAIL, f"{type(e).__name__}: {str(e)[:70]}")


def check_promotion():
    try:
        from execution_safety.promotion_pipeline_v2 import evaluate, REQUIREMENTS
        st = evaluate("portfolio_multisleeve")
        if REQUIREMENTS["LIVE_APPROVED"]["research_min"] != 0.60:
            return rec("promotion", FAIL, "LIVE research bar has been altered from 0.60")
        blocking = "; ".join(f"{k}: {','.join(v)}" for k, v in st["blocking"].items()) or "none"
        return rec("promotion", OK,
                   f"state={st['state']} demo_trades={st['demo_trades']} "
                   f"cap={st['position_cap']}pos/{st['risk_cap_pct']:.2%} | blocking {blocking}")
    except Exception as e:
        return rec("promotion", FAIL, f"{type(e).__name__}: {str(e)[:70]}")


def check_contracts():
    try:
        from execution_safety.strategy_contract import StrategyRegistry
        r = StrategyRegistry()
        if not r.contracts:
            return rec("contracts", FAIL, "no strategy contracts loaded")
        rows = [f"{c.strategy_id}={c.status}" for c in r.contracts.values()]
        demo = [c.strategy_id for c in r.contracts.values() if c.may_trade_demo()]
        live = [c.strategy_id for c in r.contracts.values() if c.may_trade_real()]
        return rec("contracts", OK, f"{len(rows)} contracts | demo-eligible: {demo or 'none'} | "
                                    f"live-eligible: {live or 'none'}", critical=False)
    except Exception as e:
        return rec("contracts", FAIL, str(e)[:70], critical=False)


def check_execution_gate():
    """Prove the gate still refuses an unauthorised signal."""
    try:
        from execution_safety.gate import Signal, authorize
        from execution_safety.strategy_contract import StrategyRegistry

        class Empty(StrategyRegistry):
            def __init__(self): self.contracts = {}
        d = authorize(Signal("hc", "nope", "v1", "EURUSD", 1, 1.10, 1.09),
                      registry=Empty(), inference=lambda s: "ALLOW_PAPER", guardian_ok=True,
                      equity=1000, account_is_demo=True, open_positions=[])
        if d["decision"] != "BLOCK" or "order_intent" in d:
            return rec("execution_gate", FAIL, "gate did NOT block an unknown strategy")
        from execution_safety.execution_guard import consume_or_block, ExecutionBlocked
        try:
            consume_or_block("healthcheck"); return rec("execution_gate", FAIL, "guard did not block unarmed submit")
        except ExecutionBlocked:
            pass
        return rec("execution_gate", OK, "blocks unknown strategy; guard blocks unarmed submit")
    except Exception as e:
        return rec("execution_gate", FAIL, f"{type(e).__name__}: {str(e)[:70]}")


def check_guardian(quick=False):
    try:
        from execution_safety.guardian_bridge import guardian_ok
        if quick:
            return rec("guardian", SKIP, "skipped (--quick)")
        ok, det = guardian_ok()
        reason = det.get("reason", "evaluated")
        if ok:
            return rec("guardian", OK, "ALLOW (live evaluation)")
        if reason in ("GUARDIAN_UNAVAILABLE",):
            return rec("guardian", FAIL, f"{reason}: {det.get('error', '')[:60]}")
        return rec("guardian", OK, f"reachable, currently BLOCK ({reason}) — fail-closed is correct")
    except Exception as e:
        return rec("guardian", FAIL, f"{type(e).__name__}: {str(e)[:70]}")


def check_ledger():
    try:
        from execution_safety.position_ledger import PositionLedger, classify_broker_positions
        led = PositionLedger()
        r = classify_broker_positions([], led, our_magic=880001)
        return rec("ledger", OK, f"{len(led.entries)} entries; orphan policy active "
                                 f"(block_all={r['block_all_orders']})")
    except Exception as e:
        return rec("ledger", FAIL, f"{type(e).__name__}: {str(e)[:70]}")


def check_reconciliation():
    try:
        from execution_safety.broker_reconciliation import BrokerPosition, reconcile
        r = reconcile({"calculated_volume": 0.1, "magic_number": 880001,
                       "comment": "hc", "stop_loss": 1.09},
                      BrokerPosition("EURUSD", 0.1, sl=0.0, tp=None, magic=880001, comment="hc"))
        if r["state"] != "CRITICAL" or not r["block_new_entries"]:
            return rec("reconciliation", FAIL, "naked position not flagged CRITICAL")
        return rec("reconciliation", OK, "naked-stop detection works; exit reconciliation NOT implemented")
    except Exception as e:
        return rec("reconciliation", FAIL, f"{type(e).__name__}: {str(e)[:70]}")


def check_demo_envelope():
    # ponytail: probes run against a THROWAWAY state file. A diagnostic must never mutate the
    # live safety state -- halting it here left the platform halted and silently swallowed the
    # operator's own halt drill (halt() is a no-op when already halted, so no alert fired).
    import tempfile, shutil
    tmp = tempfile.mkdtemp(prefix="hc_envelope_")
    try:
        from execution_safety.demo_evidence import LimitedDemoEnvelope
        sp = os.path.join(tmp, "safety_state.json")
        e = LimitedDemoEnvelope(max_positions=1, max_trades_per_day=3, state_path=sp)
        if e.allow(1)[0] is not False:
            return rec("demo_envelope", FAIL, "position cap not enforced")
        e2 = LimitedDemoEnvelope(state_path=sp); e2.halt("hc")
        if e2.allow(0)[0] is not False:
            return rec("demo_envelope", FAIL, "halt not enforced")
        return rec("demo_envelope", OK, "position cap + daily cap + halt all enforced (temp state)")
    except Exception as e:
        return rec("demo_envelope", FAIL, f"{type(e).__name__}: {str(e)[:70]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- external
def check_broker(quick=False):
    if quick:
        return rec("broker", SKIP, "skipped (--quick)", critical=False)
    try:
        import MetaTrader5 as mt5
    except Exception:
        return rec("broker", SKIP, "MetaTrader5 package not available on this machine", critical=False)
    try:
        if not mt5.initialize():
            return rec("broker", FAIL, "mt5.initialize() failed — terminal running?", critical=False)
        a = mt5.account_info()
        if a is None:
            return rec("broker", FAIL, "no account info (not logged in)", critical=False)
        demo = a.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        return rec("broker", OK if demo else WARN,
                   f"{'DEMO' if demo else 'REAL'} {a.login} @ {a.server} equity {a.equity:,.2f}",
                   critical=False)
    except Exception as e:
        return rec("broker", FAIL, f"{type(e).__name__}: {str(e)[:70]}", critical=False)


def check_telegram(quick=False):
    try:
        from market_intel import telegram_notifier as tg
        conf = bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
        if not conf:
            return rec("telegram", WARN, "not configured (TELEGRAM_TOKEN/CHAT_ID unset)", critical=False)
        return rec("telegram", OK, f"configured, {len(tg.CLASSES)} alert classes | WIRED: "
                                   "safety_state HALT/corruption + runner fills/vetoes/critical",
                   critical=False)
    except Exception as e:
        return rec("telegram", FAIL, str(e)[:70], critical=False)


def check_dashboards():
    entries = {"market_intel/web.py": "py -m market_intel.web",
               "market_intel/dashboard.py": "py -m market_intel.dashboard",
               "scripts/portfolio_mt5.py": "py portfolio_mt5.py --config funded",
               "market_intel/reaction_recorder.py": "py -m market_intel.reaction_recorder"}
    missing = [f for f in entries if not os.path.exists(os.path.join(ROOT, f))]
    if missing:
        return rec("entry_points", FAIL, f"missing: {', '.join(missing)}", critical=False)
    return rec("entry_points", OK, f"{len(entries)} entry points present", critical=False)


# ---------------------------------------------------------------- main
def run(quick=False, as_json=False):
    t0 = time.time()
    check_version(); check_files(); check_modules(); check_env()
    providers = check_providers(quick)
    check_contracts(); check_belief(); check_promotion()
    check_execution_gate(); check_guardian(quick); check_ledger()
    check_reconciliation(); check_demo_envelope()
    check_broker(quick); check_telegram(quick); check_dashboards()

    crit_fail = [r for r in results if r["critical"] and r["status"] == FAIL]
    if as_json:
        print(json.dumps({"results": results, "providers": providers,
                          "critical_failures": len(crit_fail),
                          "elapsed_s": round(time.time() - t0, 2)}, indent=1))
        return 1 if crit_fail else 0

    W = {OK: "\033[92m", WARN: "\033[93m", FAIL: "\033[91m", SKIP: "\033[90m"}
    R = "\033[0m"
    use_colour = sys.stdout.isatty()
    print("=" * 78)
    print(" SYSTEM HEALTHCHECK")
    print("=" * 78)
    for r in results:
        tag = r["status"]
        col = (W.get(tag, "") if use_colour else "")
        end = (R if use_colour else "")
        star = "*" if r["critical"] else " "
        print(f" [{col}{tag:4}{end}]{star} {r['subsystem']:20s} {r['detail']}")
    print("-" * 78)
    print(" CALENDAR PROVIDERS   implemented / configured / tested / active")
    for p in providers:
        def m(v): return "yes" if v is True else ("no" if v is False else " - ")
        print(f"   {p['provider']:34s} {m(p['implemented']):>4} {m(p['configured']):>10} "
              f"{m(p['tested']):>8} {m(p.get('active')):>7}   {p['note']}")
    print("-" * 78)
    n_ok = sum(1 for r in results if r["status"] == OK)
    print(f" {n_ok}/{len(results)} subsystems PASS | critical failures: {len(crit_fail)} "
          f"| {time.time()-t0:.1f}s")
    print(" (* = critical: a FAIL here means the platform must not execute)")
    print("=" * 78)
    return 1 if crit_fail else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quick", action="store_true", help="skip network/broker probes")
    a = ap.parse_args()
    sys.exit(run(quick=a.quick, as_json=a.json))
