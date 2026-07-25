"""startup.py -- Startup Diagnostics. Every runner should call `banner()` before doing anything,
so what is printed is ALWAYS live state, never a hardcoded status string.

    py startup.py                      # print the diagnostics banner
    from startup import banner; banner()   # inside a runner

Prints: repository version, module versions, configured providers, belief status, guardian status,
promotion state, telegram status, calendar provider, broker connectivity.
Every line is computed at call time. Nothing here is a literal claim about system state.
"""
from __future__ import annotations
import json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _version():
    try:
        v = json.load(open(os.path.join(ROOT, "VERSION.json")))
        return f"{v['version']} @ {v['commit_short']} ({v['branch']})"
    except Exception as e:
        return f"UNKNOWN ({type(e).__name__})"


def _deployment():
    try:
        from deploy import verify
        ok, r = verify()
        if "error" in r:
            return f"unverified ({r['error'][:44]})"
        return f"{r['verdict']} {r['n_ok']} files ok" + \
               (f", {len(r['missing'])} missing" if r["missing"] else "") + \
               (f", {len(r['changed'])} modified" if r["changed"] else "")
    except Exception as e:
        return f"unavailable ({type(e).__name__})"


def _modules():
    mods = {"gate": "execution_safety.gate", "belief_v2": "execution_safety.belief_graph_v2",
            "promotion_v2": "execution_safety.promotion_pipeline_v2",
            "guard": "execution_safety.execution_guard", "state": "market_intel.state",
            "calendar": "market_intel.calendar_feed"}
    okc = 0
    for m in mods.values():
        try:
            __import__(m); okc += 1
        except Exception:
            pass
    return f"{okc}/{len(mods)} core modules import"


def _providers():
    conf = []
    for k, label in (("FRED_API_KEY", "FRED"), ("FINNHUB_TOKEN", "Finnhub"),
                     ("TRADINGECONOMICS_KEY", "TradingEconomics"), ("FXSTREET_URL", "FXStreet"),
                     ("TRADINGVIEW_MCP_URL", "TradingView-MCP")):
        if os.environ.get(k):
            conf.append(label)
    if os.environ.get("FAIRECONOMY_DISABLED") != "1":
        conf.insert(0, "FairEconomy(no-key)")
    if os.environ.get("FOREXFACTORY_ENABLED") == "1":
        conf.append("ForexFactory-SCRAPE")
    return ", ".join(conf) or "none configured"


def _calendar_active():
    try:
        from market_intel import calendar_feed as cf
        ev = cf.load()
        if not ev:
            return "no events (all providers empty/unreachable)"
        prov = getattr(ev[0], "provider", "unknown")
        fc = sum(1 for e in ev if getattr(e, "forecast", None) is not None)
        return f"{prov}: {len(ev)} events, {fc} with forecast"
    except Exception as e:
        return f"error ({type(e).__name__})"


def _belief():
    try:
        from execution_safety.belief_graph_v2 import BeliefGraphV2
        g = BeliefGraphV2()
        if not g.strategies:
            return "no strategies in belief_v2.json"
        s = g.get("portfolio_multisleeve")
        return (f"research {s.research_belief():.4f} | operational {s.operational_belief():.4f} "
                f"| evidence {len(s.evidence)}")
    except Exception as e:
        return f"unavailable ({type(e).__name__})"


def _promotion():
    try:
        from execution_safety.promotion_pipeline_v2 import evaluate
        st = evaluate("portfolio_multisleeve")
        blocking = "; ".join(f"{k}:{','.join(v)}" for k, v in st["blocking"].items()) or "none"
        return (f"{st['state']} | demo_trades {st['demo_trades']} | "
                f"caps {st['position_cap']}pos/{st['risk_cap_pct']:.2%} | blocking {blocking}")
    except Exception as e:
        return f"unavailable ({type(e).__name__})"


def _guardian():
    try:
        from execution_safety.guardian_bridge import guardian_ok
        ok, det = guardian_ok()
        return f"{'ALLOW' if ok else 'BLOCK'} ({det.get('reason', 'live evaluation')})"
    except Exception as e:
        return f"unavailable ({type(e).__name__})"


def _telegram():
    conf = bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
    return ("configured — NOTE: no runner currently emits alerts (not integrated)"
            if conf else "not configured")


def _broker():
    try:
        import MetaTrader5 as mt5
    except Exception:
        return "MetaTrader5 package not available on this machine"
    try:
        if not mt5.initialize():
            return "initialize() failed — is the terminal running?"
        a = mt5.account_info()
        if a is None:
            return "connected, not logged in"
        kind = "DEMO" if a.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "REAL"
        return f"{kind} {a.login} @ {a.server} | equity {a.equity:,.2f}"
    except Exception as e:
        return f"error ({type(e).__name__})"


def diagnostics() -> dict:
    return {"version": _version(), "deployment": _deployment(), "modules": _modules(),
            "providers_configured": _providers(), "calendar_active": _calendar_active(),
            "belief": _belief(), "promotion": _promotion(), "guardian": _guardian(),
            "telegram": _telegram(), "broker": _broker()}


def banner(title="STARTUP DIAGNOSTICS") -> dict:
    d = diagnostics()
    w = 78
    print("=" * w)
    print(f" {title}")
    print("=" * w)
    for k, v in d.items():
        print(f"  {k:22s} {v}")
    print("=" * w)
    return d


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    print(json.dumps(diagnostics(), indent=1)) if a.json else banner()
