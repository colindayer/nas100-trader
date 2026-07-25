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
    """Hard operating limits for LIMITED_DEMO, backed by PERSISTENT state.

    V-01/V-02 fix: the daily counter and the halt live in registry/safety_state.json, so they
    survive process restart, VPS reboot and power loss. This class holds NO authoritative state.
    """
    def __init__(self, max_positions=1, max_trades_per_day=3, risk_pct=0.001,
                 state_path=None, equity=None):
        from . import safety_state as _ss
        self._ss = _ss
        self.state_path = state_path or _ss.STATE_PATH
        self.max_positions = max_positions
        self.max_trades_per_day = max_trades_per_day
        self.risk_pct = risk_pct
        st, notes = _ss.load(self.state_path, equity=equity)
        self.load_notes = notes

    # ---- authoritative reads come from disk every time ----
    @property
    def _state(self):
        st, _ = self._ss.load(self.state_path)
        return st

    @property
    def halted(self) -> bool:
        return self._state.halted

    @property
    def halt_reason(self):
        return self._state.halt_reason

    def trades_today(self) -> int:
        return self._state.trades_today

    def allow(self, open_positions: int) -> tuple[bool, str]:
        st = self._state                                   # re-read: another process may have halted
        if st.halted:
            return False, f"HALTED: {st.halt_reason}"
        if open_positions >= self.max_positions:
            return False, "MAX_POSITIONS"
        if st.trades_today >= self.max_trades_per_day:
            return False, "DAILY_TRADE_LIMIT"
        return True, "ok"

    def record_trade(self, intent_id: str | None = None):
        self._ss.record_trade(intent_id, path=self.state_path)

    def halt(self, reason: str):
        self._ss.halt(reason, path=self.state_path)


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
