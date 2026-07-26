"""operational_belief.py -- PHASE 702. Converts per-trade EXECUTION QUALITY into OperationalBelief
evidence. It measures whether the machine works, never whether the strategy is profitable.
P&L is deliberately NOT an input here.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from .belief_graph_v2 import Evidence

# each check contributes to execution quality; a failed CRITICAL check is a defect
CRITICAL = {"stop_verified", "reconciliation_passed", "ledger_recorded", "no_duplicate"}
CHECKS = ["stop_verified", "reconciliation_passed", "ledger_recorded", "no_duplicate",
          "symbol_mapped", "volume_correct", "guardian_approved", "broker_ack",
          "slippage_acceptable", "latency_acceptable", "exit_verified"]


@dataclass
class TradeExecutionRecord:
    trade_id: str
    symbol: str
    expected_entry: float = 0.0
    actual_entry: float = 0.0
    expected_spread: float = 0.0
    actual_spread: float = 0.0
    expected_slippage: float = 0.0
    actual_slippage: float = 0.0
    stop_verified: bool = False
    exit_verified: bool = False
    reconciliation_passed: bool = False
    ledger_recorded: bool = False
    no_duplicate: bool = True
    symbol_mapped: bool = False
    volume_correct: bool = False
    guardian_approved: bool = False
    broker_ack: bool = False
    execution_latency_ms: float = 0.0
    broker_retcode: int = 0
    defects: list = field(default_factory=list)
    # --- context at entry (Market Memory prerequisite). Retrofitting is impossible, so it is
    # captured from trade one. NOT an operational-quality input: it never affects `quality()`. ---
    regime_at_entry: str = ""            # e.g. "up/highvol" from market_intel.state
    session_at_entry: str = ""
    kill_zones_at_entry: str = ""
    volatility_regime: str = ""
    macro_risk_state: str = ""           # from macro_board risk claim, if available

    # derived checks
    @property
    def slippage_acceptable(self) -> bool:
        tol = max(abs(self.expected_slippage) * 3, abs(self.expected_entry) * 0.0005, 1e-9)
        return abs(self.actual_slippage) <= tol

    @property
    def latency_acceptable(self) -> bool:
        return 0 <= self.execution_latency_ms <= 3000

    def failed_checks(self) -> list:
        out = []
        for c in CHECKS:
            v = getattr(self, c, None)
            v = v if isinstance(v, bool) else bool(v)
            if not v:
                out.append(c)
        return out

    def critical_failures(self) -> list:
        return [c for c in self.failed_checks() if c in CRITICAL]

    def quality(self) -> float:
        passed = len(CHECKS) - len(self.failed_checks())
        return passed / len(CHECKS)

    def to_dict(self): return {**asdict(self), "quality": round(self.quality(), 3),
                               "failed_checks": self.failed_checks()}


def to_evidence(rec: TradeExecutionRecord, evidence_class="DemoExecution") -> Evidence:
    """One trade -> one operational evidence item. A critical failure is evidence AGAINST."""
    crit = rec.critical_failures()
    supports = not crit and rec.quality() >= 0.8
    # per-trade weight is deliberately small: operational confidence accrues over many trades
    weight = round(0.25 + 0.35 * rec.quality(), 3) if supports else round(0.6 + 0.4 * len(crit), 3)
    note = (f"{rec.symbol} q={rec.quality():.2f}"
            + (f" CRITICAL:{','.join(crit)}" if crit else "")
            + (f" failed:{','.join(rec.failed_checks())}" if rec.failed_checks() and not crit else ""))
    return Evidence(evidence_id=f"exec-{rec.trade_id}", evidence_class=evidence_class,
                    supports=supports, weight=weight, note=note)
