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
    # True ONLY when the broker refused the order AND the position list was successfully queried
    # and confirmed empty for our magic. Never inferred from a retcode alone.
    order_rejected_no_position: bool = False
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

    # Checks that describe a POSITION. If the broker refused the order, no position exists, so
    # these are NOT APPLICABLE -- they are not failures. See order_rejected_no_position.
    POSITION_CHECKS = ("stop_verified", "reconciliation_passed", "volume_correct")

    def critical_failures(self) -> list:
        """Critical == 'we may be holding something unsafe'.

        A broker rejection is not that. Nothing was opened, so there is no unverified stop and
        nothing to reconcile. Scoring a rejection as a critical execution defect halted the demo
        campaign on 2026-07-30 and again on 2026-08-02 for FundedNext retcode 10026
        (TRADE_RETCODE_SERVER_DISABLES_AT), and each time wrote weight-1.4 evidence AGAINST
        operational belief for a failure that never happened.

        This is a CLASSIFICATION fix, not a relaxation: the exemption applies only when we have
        POSITIVE proof that no position exists (see _capture_execution). If the broker could not
        be queried, order_rejected_no_position stays False and every check fails as before --
        fail-closed, because an unconfirmed order is exactly the dangerous case.
        """
        failed = self.failed_checks()
        if self.order_rejected_no_position:
            failed = [c for c in failed if c not in self.POSITION_CHECKS]
        return [c for c in failed if c in CRITICAL]

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
