"""belief_reader.py -- PHASE 601 gap closure. Reads the research Belief Graph SNAPSHOT (a data
artifact, not research code -- the firewall stays intact) and converts a hypothesis posterior into
an inference decision. FAIL CLOSED: no snapshot, unknown hypothesis, or stale snapshot => BLOCK.

[STATUS: LEGACY v1 belief store. --live still uses it; --demo-limited uses belief_graph_v2.]
"""
from __future__ import annotations
import json, math, os, time

SNAPSHOT = "registry/belief_graph.json"
DEFAULT_THRESHOLD = 0.60
MAX_AGE_DAYS = 90            # a stale belief is not evidence


def _sigmoid(x): return 1 / (1 + math.exp(-x))
def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6); return math.log(p / (1 - p))


def posterior(hypothesis: str, path: str = SNAPSHOT) -> float | None:
    """Recompute the posterior from prior + evidence log-odds. None if unavailable."""
    if not os.path.exists(path):
        return None
    try:
        data = json.load(open(path))
    except Exception:
        return None
    h = data.get(hypothesis)
    if not h:
        return None
    lo = _logit(h.get("prior", 0.25))
    for e in h.get("evidence", []):
        w = float(e.get("weight", 0.0))
        lo += w if e.get("supports") else -w
    return _sigmoid(lo)


def decide(hypothesis: str, threshold: float = DEFAULT_THRESHOLD,
           path: str = SNAPSHOT) -> tuple[str, dict]:
    """Return (decision, detail). Decisions: ALLOW_PAPER | BLOCK | RESEARCH_ONLY."""
    if not os.path.exists(path):
        return "RESEARCH_ONLY", {"reason": "NO_BELIEF_SNAPSHOT", "path": path}
    age_days = (time.time() - os.path.getmtime(path)) / 86400
    if age_days > MAX_AGE_DAYS:
        return "RESEARCH_ONLY", {"reason": "BELIEF_SNAPSHOT_STALE", "age_days": round(age_days, 1)}
    p = posterior(hypothesis, path)
    if p is None:
        return "RESEARCH_ONLY", {"reason": "HYPOTHESIS_NOT_IN_GRAPH", "hypothesis": hypothesis}
    if p < threshold:
        return "BLOCK", {"reason": "POSTERIOR_BELOW_THRESHOLD", "posterior": round(p, 4),
                         "threshold": threshold}
    return "ALLOW_PAPER", {"posterior": round(p, 4), "threshold": threshold,
                           "age_days": round(age_days, 1)}
