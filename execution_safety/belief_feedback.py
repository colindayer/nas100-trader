"""belief_feedback.py -- closes the PHASE 601 loop: realised broker P&L -> Belief Graph evidence.
Reads CLOSED deals for our magic from MT5 history, computes realised expectancy with a bootstrap CI,
and writes an evidence entry into the belief snapshot. This is the ONLY legitimate way a strategy's
posterior rises: by producing real, measured results.

[STATUS: ORPHANED - writes the v1 store; no runner calls it. See ARCHITECTURE_STATE_2026 gap 8.]
"""
from __future__ import annotations
import json, math, os
from datetime import datetime, timedelta, timezone

SNAPSHOT = "registry/belief_graph.json"
MIN_TRADES = 30            # below this, evidence weight is capped hard


def closed_trades(magic: int, days: int = 365) -> list[dict]:
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return []
        to = datetime.now(timezone.utc); frm = to - timedelta(days=days)
        deals = mt5.history_deals_get(frm, to) or []
        return [{"symbol": d.symbol, "profit": d.profit, "time": d.time, "volume": d.volume}
                for d in deals if getattr(d, "magic", None) == magic and d.entry == mt5.DEAL_ENTRY_OUT]
    except Exception:
        return []


def summarise(trades: list[dict], equity: float) -> dict | None:
    if not trades or equity <= 0:
        return None
    import statistics as st
    r = [t["profit"] / equity for t in trades]
    n = len(r)
    mean = sum(r) / n
    sd = st.pstdev(r) or 1e-9
    se = sd / math.sqrt(n)
    lo, hi = mean - 1.96 * se, mean + 1.96 * se           # normal-approx CI
    return {"n": n, "mean_return": mean, "ci": (lo, hi),
            "ci_excludes_zero": bool(lo > 0 or hi < 0),
            "win_rate": sum(1 for x in r if x > 0) / n,
            "total_return": sum(r)}


def update_belief(hypothesis: str, summary: dict, path: str = SNAPSHOT,
                  experiment: str = "live_demo_realised") -> dict:
    """Write realised-performance evidence. Weight scales with sample size and CI separation,
    and is CAPPED until MIN_TRADES so a handful of lucky fills cannot unblock trading."""
    data = json.load(open(path)) if os.path.exists(path) else {}
    h = data.setdefault(hypothesis, {"name": hypothesis, "statement": hypothesis,
                                     "prior": 0.25, "evidence": []})
    n = summary["n"]
    supports = summary["mean_return"] > 0 and summary["ci_excludes_zero"]
    size = min(1.5, math.log10(max(n, 10)) / 3)
    weight = round(0.3 + size, 3)
    if n < MIN_TRADES:                                     # small sample => weak evidence, both ways
        weight = min(weight, 0.4)
    h["evidence"] = [e for e in h["evidence"] if e.get("experiment") != experiment]
    h["evidence"].append({"experiment": experiment, "supports": bool(supports), "weight": weight,
        "note": (f"realised demo: n={n}, mean {summary['mean_return']:+.4%}/trade, "
                 f"win {summary['win_rate']:.0%}, CI {'excludes' if summary['ci_excludes_zero'] else 'includes'} 0"
                 + (" [SMALL SAMPLE: weight capped]" if n < MIN_TRADES else ""))})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w"), indent=1)
    return h


def run(hypothesis="H_portfolio_multisleeve", magic=880001, equity=None):
    try:
        import MetaTrader5 as mt5
        mt5.initialize(); equity = equity or mt5.account_info().equity
    except Exception:
        if equity is None:
            return {"error": "MT5 unavailable and no equity supplied"}
    tr = closed_trades(magic)
    s = summarise(tr, equity)
    if not s:
        return {"status": "no closed trades yet", "magic": magic}
    h = update_belief(hypothesis, s)
    from .belief_reader import decide
    d, det = decide(hypothesis)
    return {"summary": s, "new_decision": d, "detail": det, "evidence_count": len(h["evidence"])}
