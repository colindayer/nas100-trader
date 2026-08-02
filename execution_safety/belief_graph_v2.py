"""belief_graph_v2.py -- PHASE 702. TWO independent beliefs, so evidence cannot leak between them.

  ResearchBelief    : does this strategy have statistical EDGE?      (slow; research evidence only)
  OperationalBelief : does this system EXECUTE correctly?            (demo/live execution evidence only)

The circular dependency is broken by design: operational evidence is collected under
LIMITED_DEMO (authorised by *research* evidence), and it can never inflate ResearchBelief.
"""
from __future__ import annotations
import hashlib, json, math, os, tempfile, time
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
    # An annulled item stays in the record forever -- this is an append-only audit trail, not a
    # delete button -- but stops contributing belief and stops counting as a defect. Annulment is
    # ONLY for evidence that is factually wrong about what happened, never for evidence that is
    # merely unwelcome. It requires a human actor and a reason, both recorded below.
    annulled_by: str | None = None
    annulled_reason: str = ""
    annulled_ts: float | None = None

    @property
    def annulled(self) -> bool:
        return self.annulled_by is not None

    def research_logodds(self) -> float:
        if self.annulled:
            return 0.0
        f = EVIDENCE_CLASSES.get(self.evidence_class, {}).get("research_factor", 0.0)
        return (self.weight if self.supports else -self.weight) * f

    def ops_logodds(self) -> float:
        if self.annulled:
            return 0.0
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
                if not e.supports and not e.annulled
                and e.evidence_class in ("DemoExecution", "LiveExecution", "Shadow")]

    def count(self, cls: str) -> int:
        return sum(1 for e in self.evidence if e.evidence_class == cls and not e.annulled)


class BeliefGraphV2:
    def __init__(self, path=STORE):
        self.path = path; self.strategies: dict[str, StrategyBeliefs] = {}
        self.corrupt = False; self.load()

    def get(self, sid: str) -> StrategyBeliefs:
        return self.strategies.setdefault(sid, StrategyBeliefs(strategy_id=sid))

    def add(self, sid: str, ev: Evidence):
        if ev.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(f"unknown evidence class {ev.evidence_class}")
        s = self.get(sid)
        s.evidence = [e for e in s.evidence if e.evidence_id != ev.evidence_id]   # idempotent
        s.evidence.append(ev); self.save(); return s

    def annul(self, sid: str, evidence_id: str, actor: str, reason: str) -> dict:
        """Neutralise ONE evidence item that is factually wrong about what happened.

        Not a delete: the item stays in the store with the actor and reason attached, and remains
        visible in the audit trail. It simply stops contributing belief and stops counting as a
        defect or as a demo trade.

        This exists because a broker rejection was recorded as a failed execution -- an event that
        never occurred -- which drove the strategy back to RESEARCH_ONLY with no way out. The bug
        is fixed; the false record still had to be correctable.

        Annul evidence that misdescribes reality. NEVER annul evidence that is merely unwelcome:
        a real defect that is annulled away is how a safety system becomes decorative.
        """
        if not actor or not reason:
            raise ValueError("annul requires both an actor and a reason — it is a human act")
        s = self.get(sid)
        hits = [e for e in s.evidence if e.evidence_id == evidence_id]
        if not hits:
            return {"error": f"no evidence {evidence_id} on {sid}",
                    "available": [e.evidence_id for e in s.evidence]}
        ev = hits[0]
        if ev.annulled:
            return {"error": f"{evidence_id} already annulled by {ev.annulled_by}"}
        ev.annulled_by, ev.annulled_reason, ev.annulled_ts = actor, reason, time.time()
        self.save()
        from .safety_state import audit
        audit("EVIDENCE_ANNULLED", {"strategy": sid, "evidence_id": evidence_id,
                                    "actor": actor, "reason": reason, "note": ev.note})
        return {"annulled": evidence_id, "actor": actor, "reason": reason, "note": ev.note}

    def save(self):
        """V-05: atomic + fsynced + backed-up write under an advisory lock. A crash mid-write can
        no longer truncate the store, and a corrupt store no longer silently reads as EMPTY."""
        from .safety_state import acquire, release
        payload = {k: {**asdict(v), "evidence": [asdict(e) for e in v.evidence]}
                   for k, v in self.strategies.items()}
        body = {"schema_version": 2, "payload": payload,
                "digest": hashlib.sha256(json.dumps(payload, sort_keys=True,
                                                    separators=(",", ":")).encode()).hexdigest()[:32]}
        d = os.path.dirname(self.path) or "."
        os.makedirs(d, exist_ok=True)
        lp = acquire(self.path)
        try:
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".belief_", suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(body, f, indent=1); f.flush(); os.fsync(f.fileno())
                if os.path.exists(self.path):
                    try:
                        import shutil; shutil.copy2(self.path, self.path + ".bak")
                    except Exception:
                        pass
                os.replace(tmp, self.path)
            except Exception:
                try: os.unlink(tmp)
                except Exception: pass
                raise
        finally:
            release(lp)

    def load(self):
        """V-05: verifies the digest and recovers from backup. Corruption sets self.corrupt so the
        caller can fail closed instead of seeing a silently-empty graph."""
        self.corrupt = False
        if not os.path.exists(self.path): return
        def _read(p):
            try: return json.load(open(p))
            except Exception: return None
        data = _read(self.path)
        if data is None:
            data = _read(self.path + ".bak")
            if data is None:
                self.corrupt = True; return
        if isinstance(data, dict) and "payload" in data and "digest" in data:
            calc = hashlib.sha256(json.dumps(data["payload"], sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()[:32]
            if calc != data["digest"]:
                bak = _read(self.path + ".bak")
                if bak and bak.get("digest") == hashlib.sha256(
                        json.dumps(bak.get("payload", {}), sort_keys=True,
                                   separators=(",", ":")).encode()).hexdigest()[:32]:
                    data = bak
                else:
                    self.corrupt = True; return
            data = data["payload"]
        for k, d in data.items():
            s = StrategyBeliefs(d["strategy_id"], d.get("research_prior", .25), d.get("ops_prior", .20))
            s.evidence = [Evidence(**e) for e in d.get("evidence", [])]
            self.strategies[k] = s


# ---------------------------------------------------------------- admin CLI
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="inspect and annul belief evidence")
    ap.add_argument("--sid", default="portfolio_multisleeve")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--annul", metavar="EVIDENCE_ID")
    ap.add_argument("--actor", default="")
    ap.add_argument("--reason", default="")
    a = ap.parse_args()
    g = BeliefGraphV2()
    if g.corrupt:
        raise SystemExit("belief store CORRUPT — refusing to act")
    s = g.get(a.sid)
    if a.annul:
        r = g.annul(a.sid, a.annul, a.actor, a.reason)
        print(r)
    print(f"\n{a.sid}: research={s.research_belief():.4f} ops={s.operational_belief():.4f} "
          f"demo_trades={s.count('DemoExecution')} defects={len(s.defects())}")
    for e in s.evidence:
        flag = f"  ANNULLED by {e.annulled_by}" if e.annulled else ""
        print(f"  {e.evidence_id:<46} {e.evidence_class:<14} supports={str(e.supports):<5} "
              f"w={e.weight}{flag}\n      {e.note[:96]}")
