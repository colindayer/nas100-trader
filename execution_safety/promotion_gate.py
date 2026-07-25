"""promotion_gate.py -- the promotion RULE, defined BEFORE any strategy qualifies. NEEDS_REPLICATION
-> PAPER_APPROVED requires ALL criteria. Fail closed: missing evidence => not eligible. Nothing is
promoted because it's exciting; it's promoted because it meets every threshold, provably.

[STATUS: SUPERSEDED by promotion_pipeline_v2.py (5-state). Used only by test_promotion.]
"""
from __future__ import annotations

PROMOTION_RULES = {
    "min_independent_periods": 2,       # replicated across multiple time periods
    "min_sharpe": 0.5,                  # statistical threshold
    "require_ci_excludes_zero": True,   # effect distinguishable from noise
    "require_after_costs": True,        # survives realistic transaction costs
    "min_shadow_signals": 100,          # passed shadow execution...
    "min_shadow_days": 30,              # ...over enough calendar time
    "require_no_operational_issues": True,
    "require_frozen_version": True,     # exact deployable code_commit pinned
    "require_prop_sim_for_firm": True,  # simulated against the exact firm config
}


def can_promote(ev: dict) -> dict:
    """ev: candidate evidence. Returns eligibility + the criteria that failed. Explicit, auditable."""
    R = PROMOTION_RULES; fails = []
    if ev.get("independent_periods", 0) < R["min_independent_periods"]:
        fails.append(f"needs >={R['min_independent_periods']} independent periods (have {ev.get('independent_periods',0)})")
    if ev.get("sharpe", -9) < R["min_sharpe"]:
        fails.append(f"Sharpe {ev.get('sharpe')} < {R['min_sharpe']}")
    ci = ev.get("ci")
    if R["require_ci_excludes_zero"] and not (ci and (ci[0] > 0 or ci[1] < 0)):
        fails.append("CI does not exclude zero")
    if R["require_after_costs"] and not ev.get("after_costs"):
        fails.append("not validated after realistic costs")
    if ev.get("shadow_signals", 0) < R["min_shadow_signals"]:
        fails.append(f"shadow signals {ev.get('shadow_signals',0)} < {R['min_shadow_signals']}")
    if ev.get("shadow_days", 0) < R["min_shadow_days"]:
        fails.append(f"shadow days {ev.get('shadow_days',0)} < {R['min_shadow_days']}")
    if R["require_no_operational_issues"] and ev.get("operational_issues", 1) != 0:
        fails.append("unresolved operational issues in shadow")
    if R["require_frozen_version"] and not ev.get("frozen_code_commit"):
        fails.append("no frozen code_commit")
    if R["require_prop_sim_for_firm"] and not ev.get("prop_sim_firm"):
        fails.append("no prop-firm simulation for a target firm")
    return {"eligible": not fails, "target_status": "PAPER_APPROVED" if not fails else "NEEDS_REPLICATION",
            "failed_criteria": fails, "rules": R}
