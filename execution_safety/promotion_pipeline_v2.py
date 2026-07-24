"""promotion_pipeline_v2.py -- PHASE 702. Five explicit states. The LIVE research bar is UNCHANGED
at 0.60. Limited demo is authorised by research evidence at a *different, purpose-specific* bar --
capital is not at risk there, its job is to collect operational evidence. No threshold was lowered.
"""
from __future__ import annotations
from .belief_graph_v2 import BeliefGraphV2, StrategyBeliefs

STATES = ["RESEARCH_ONLY", "SHADOW_APPROVED", "LIMITED_DEMO_APPROVED",
          "FULL_DEMO_APPROVED", "LIVE_APPROVED"]

REQUIREMENTS = {
    "SHADOW_APPROVED": dict(
        research_min=0.40, ops_min=0.00, min_demo_trades=0, max_critical_defects=0,
        rationale="Research suggests the idea is worth observing. Shadow places no orders."),
    "LIMITED_DEMO_APPROVED": dict(
        research_min=0.50, ops_min=0.00, min_demo_trades=0, max_critical_defects=0,
        min_shadow_evidence=1,
        rationale="Research says it DESERVES EVALUATION (not that it deserves capital). "
                  "Demo risks no money; its purpose is to collect operational evidence."),
    "FULL_DEMO_APPROVED": dict(
        research_min=0.55, ops_min=0.70, min_demo_trades=30, max_critical_defects=0,
        rationale="Execution demonstrated correct over a meaningful sample."),
    "LIVE_APPROVED": dict(
        research_min=0.60, ops_min=0.85, min_demo_trades=100, max_critical_defects=0,
        rationale="UNCHANGED live bar: real statistical edge AND proven execution."),
}


def evaluate(sid: str, graph: BeliefGraphV2 | None = None) -> dict:
    g = graph or BeliefGraphV2()
    s = g.get(sid)
    rb, ob = s.research_belief(), s.operational_belief()
    demo_n = s.count("DemoExecution")
    defects = s.defects()
    reached, blocking = "RESEARCH_ONLY", {}
    for st in STATES[1:]:
        r = REQUIREMENTS[st]; fails = []
        if rb < r["research_min"]:
            fails.append(f"research_belief {rb:.4f} < {r['research_min']}")
        if ob < r["ops_min"]:
            fails.append(f"operational_belief {ob:.4f} < {r['ops_min']}")
        if demo_n < r["min_demo_trades"]:
            fails.append(f"demo_trades {demo_n} < {r['min_demo_trades']}")
        if len(defects) > r["max_critical_defects"]:
            fails.append(f"{len(defects)} outstanding defect(s)")
        if r.get("min_shadow_evidence") and s.count("Shadow") < r["min_shadow_evidence"]:
            fails.append(f"shadow_evidence {s.count('Shadow')} < {r['min_shadow_evidence']}")
        if fails:
            blocking[st] = fails
            break
        reached = st
    return {"strategy_id": sid, "state": reached, "research_belief": round(rb, 4),
            "operational_belief": round(ob, 4), "demo_trades": demo_n,
            "outstanding_defects": defects, "blocking": blocking,
            "next_state": STATES[STATES.index(reached) + 1] if reached != "LIVE_APPROVED" else None,
            "may_trade_demo": reached in ("LIMITED_DEMO_APPROVED", "FULL_DEMO_APPROVED", "LIVE_APPROVED"),
            "may_trade_real": reached == "LIVE_APPROVED",
            "position_cap": 1 if reached == "LIMITED_DEMO_APPROVED" else
                            (3 if reached == "FULL_DEMO_APPROVED" else
                             (15 if reached == "LIVE_APPROVED" else 0)),
            "risk_cap_pct": 0.001 if reached == "LIMITED_DEMO_APPROVED" else
                            (0.005 if reached == "FULL_DEMO_APPROVED" else
                             (0.01 if reached == "LIVE_APPROVED" else 0.0))}
