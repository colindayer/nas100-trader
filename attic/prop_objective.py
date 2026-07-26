"""prop_objective.py -- PHASE 601 Stage 5. Firm-configuration abstraction + prop-survival estimates.
Not one hardcoded firm; versioned configs. A strategy cannot be PAPER_APPROVED for a firm without a
simulation against that exact config. Fail closed: unknown firm/state => cannot certify.

[STATUS: UNUSED at order time - see ARCHITECTURE_STATE_2026 gap 7.]
"""
from __future__ import annotations
import json, os
from dataclasses import dataclass, asdict

FIRM_DIR = "prop_firms"


@dataclass
class FirmConfig:
    firm_id: str
    profit_target_pct: float
    max_daily_loss_pct: float
    max_total_loss_pct: float
    drawdown_type: str                 # "static" | "trailing"
    min_trading_days: int
    max_position_size_lots: float
    prohibited_windows: list           # e.g. ["news","weekend_hold"]
    timezone: str
    commission_per_lot: float
    spread_bps: float
    consistency_rule_pct: float = 0.0  # max share of profit from one day (0 = none)


@dataclass
class PropAccountState:
    equity: float
    day_start_equity: float
    high_water_mark: float
    days_traded: int
    largest_day_profit: float


def load_firm(firm_id: str) -> FirmConfig | None:
    p = os.path.join(FIRM_DIR, f"{firm_id}.json")
    return FirmConfig(**json.load(open(p))) if os.path.exists(p) else None   # None => fail closed


def save_firm(c: FirmConfig):
    os.makedirs(FIRM_DIR, exist_ok=True)
    json.dump(asdict(c), open(os.path.join(FIRM_DIR, f"{c.firm_id}.json"), "w"), indent=1)


def survival_check(state: PropAccountState, cfg: FirmConfig, proposed_risk_pct: float) -> dict:
    """Estimate breach proximity BEFORE a trade. Deterministic guardrails (not probabilistic alpha):
    reject the trade if it could push past a daily/total limit in a single stop-out."""
    reasons = []
    day_dd = (state.day_start_equity - state.equity) / state.day_start_equity
    tot_dd = (state.high_water_mark - state.equity) / state.high_water_mark
    worst_case_day = day_dd + proposed_risk_pct          # if this trade hits its stop
    worst_case_tot = tot_dd + proposed_risk_pct
    if worst_case_day >= cfg.max_daily_loss_pct / 100: reasons.append("WOULD_RISK_DAILY_LIMIT")
    if worst_case_tot >= cfg.max_total_loss_pct / 100: reasons.append("WOULD_RISK_TOTAL_LIMIT")
    if state.days_traded < cfg.min_trading_days:
        reasons.append("MIN_TRADING_DAYS_NOT_MET")       # informational, not a block for entry
    return {"firm": cfg.firm_id, "day_drawdown_pct": round(day_dd * 100, 2),
            "total_drawdown_pct": round(tot_dd * 100, 2),
            "worst_case_day_pct": round(worst_case_day * 100, 2),
            "prop_ok": not any(r.startswith("WOULD_RISK") for r in reasons),
            "reason_codes": reasons}
