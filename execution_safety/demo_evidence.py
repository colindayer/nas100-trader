"""demo_evidence.py -- PHASE 702. Captures a LIMITED_DEMO trade's execution facts and feeds them to
OperationalBelief ONLY. Also enforces the limited-demo operating envelope.
"""
from __future__ import annotations
import json, os, time
from .belief_graph_v2 import BeliefGraphV2
from .operational_belief import TradeExecutionRecord, to_evidence
from .promotion_pipeline_v2 import evaluate

LEDGER = "registry/demo_execution_evidence.jsonl"


class LimitedDemoEnvelope:
    """Hard operating limits for LIMITED_DEMO. Any critical error -> automatic shutdown."""
    def __init__(self, max_positions=1, max_trades_per_day=3, risk_pct=0.001):
        self.max_positions = max_positions; self.max_trades_per_day = max_trades_per_day
        self.risk_pct = risk_pct; self.halted = False; self.halt_reason = None
        self._today = time.strftime("%Y-%m-%d"); self._count = 0

    def allow(self, open_positions: int) -> tuple[bool, str]:
        if self.halted: return False, f"HALTED: {self.halt_reason}"
        if time.strftime("%Y-%m-%d") != self._today:
            self._today = time.strftime("%Y-%m-%d"); self._count = 0
        if open_positions >= self.max_positions: return False, "MAX_POSITIONS"
        if self._count >= self.max_trades_per_day: return False, "DAILY_TRADE_LIMIT"
        return True, "ok"

    def record_trade(self): self._count += 1

    def halt(self, reason: str): self.halted = True; self.halt_reason = reason


def record(rec: TradeExecutionRecord, strategy_id="portfolio_multisleeve",
           graph: BeliefGraphV2 | None = None, envelope: LimitedDemoEnvelope | None = None) -> dict:
    """Persist the execution record and update OperationalBelief. Never touches ResearchBelief
    beyond the small documented DemoExecution factor in EVIDENCE_CLASSES."""
    g = graph or BeliefGraphV2()
    ev = to_evidence(rec, "DemoExecution")
    g.add(strategy_id, ev)
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps({"ts": time.time(), **rec.to_dict(),
                            "evidence": {"supports": ev.supports, "weight": ev.weight}}) + "\n")
    crit = rec.critical_failures()
    if crit and envelope is not None:
        envelope.halt(f"critical execution failure: {','.join(crit)}")
    return {"evidence": ev.note, "supports": ev.supports,
            "critical_failures": crit, "promotion": evaluate(strategy_id, g)}
