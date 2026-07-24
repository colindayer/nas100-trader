"""belief_graph_v2.py -- PHASE 702. TWO independent beliefs, so evidence cannot leak between them.

  ResearchBelief    : does this strategy have statistical EDGE?      (slow; research evidence only)
  OperationalBelief : does this system EXECUTE correctly?            (demo/live execution evidence only)

The circular dependency is broken by design: operational evidence is collected under
LIMITED_DEMO (authorised by *research* evidence), and it can never inflate ResearchBelief.
"""
from __future__ import annotations
import json, math, os, time
from dataclasses import dataclass, field, asdict

STORE = "registry/belief_v2.json"

# Evidence classes and which belief each may update.
#   research_factor: how much this class may move ResearchBelief (0 = cannot)
#   ops_factor     : how much it may move OperationalBelief
# Execution-derived classes may only ever NUDGE research belief, and their TOTAL contribution is
# capped (see MAX_EXEC_RESEARCH_LOGODDS). Without the cap, many small nudges accumulate into a large
# move -- i.e. good execution would buy edge-confidence. That is the leak this design forbids.
EXECUTION_CLASSES = {"DemoExecution", "LiveExecution", "Shadow"}
MAX_EXEC_RESEARCH_LOGODDS = 0.35        # hard ceiling on |total| research influence from execution

EVIDENCE_CLASSES = {
    "Backtest":       dict(research_factor=0.60, ops_factor=0.00),
    "WalkForward":    dict(research_factor=1.00, ops_factor=0.00),
    "Bootstrap":      dict(research_factor=0.80, ops_factor=0.00),
    "Shadow":         dict(research_factor=0.00, ops_factor=0.50),
    "DemoExecution":  dict(research_factor=0.10, ops_factor=1.00),   # limited research influence
    "LiveExecution":  dict(research_factor=0.15, ops_factor=1.00),   # never overrides research
}


def _sigmoid(x): return 1 / (1 + math.exp(-x))
def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6); return math.log(p / (1 - p))


@dataclass
class Evidence:
    evidence_id: str
    evidence_class: str          # must be in EVIDENCE_CLASSES
    supports: bool
    weight: float                # base log-odds magnitude (>0)
    note: str = ""
    ts: float = field(default_factory=time.time)

    def research_logodds(self) -> float:
        f = EVIDENCE_CLASSES.get(self.evidence_class, {}).get("research_factor", 0.0)
        return (self.weight if self.supports else -self.weight) * f

    def ops_logodds(self) -> float:
        f = EVIDENCE_CLASSES.get(self.evidence_class, {}).get("ops_factor", 0.0)
        return (self.weight if self.supports else -self.weight) * f


@dataclass
class StrategyBeliefs:
    strategy_id: str
    research_prior: float = 0.25
    ops_prior: float = 0.20          # assume execution is broken until demonstrated
    evidence: list = field(default_factory=list)

    def research_belief(self) -> float:
        base = sum(e.research_logodds() for e in self.evidence
                   if e.evidence_class not in EXECUTION_CLASSES)
        exec_lo = sum(e.research_logodds() for e in self.evidence
                      if e.evidence_class in EXECUTION_CLASSES)
        # CAP: execution quality can never accumulate into edge-confidence
        exec_lo = max(-MAX_EXEC_RESEARCH_LOGODDS, min(MAX_EXEC_RESEARCH_LOGODDS, exec_lo))
        return _sigmoid(_logit(self.research_prior) + base + exec_lo)

    def operational_belief(self) -> float:
        return _sigmoid(_logit(self.ops_prior) + sum(e.ops_logodds() for e in self.evidence))

    def defects(self) -> list:
        return [e.note for e in self.evidence
                if not e.supports and e.evidence_class in ("DemoExecution", "LiveExecution", "Shadow")]

    def count(self, cls: str) -> int:
        return sum(1 for e in self.evidence if e.evidence_class == cls)


class BeliefGraphV2:
    def __init__(self, path=STORE):
        self.path = path; self.strategies: dict[str, StrategyBeliefs] = {}; self.load()

    def get(self, sid: str) -> StrategyBeliefs:
        return self.strategies.setdefault(sid, StrategyBeliefs(strategy_id=sid))

    def add(self, sid: str, ev: Evidence):
        if ev.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(f"unknown evidence class {ev.evidence_class}")
        s = self.get(sid)
        s.evidence = [e for e in s.evidence if e.evidence_id != ev.evidence_id]   # idempotent
        s.evidence.append(ev); self.save(); return s

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump({k: {**asdict(v), "evidence": [asdict(e) for e in v.evidence]}
                   for k, v in self.strategies.items()}, open(self.path, "w"), indent=1)

    def load(self):
        if not os.path.exists(self.path): return
        try: data = json.load(open(self.path))
        except Exception: return
        for k, d in data.items():
            s = StrategyBeliefs(d["strategy_id"], d.get("research_prior", .25), d.get("ops_prior", .20))
            s.evidence = [Evidence(**e) for e in d.get("evidence", [])]
            self.strategies[k] = s
