"""Bot and Signal — the leaf both the controller and candidate bots import.

Extracted so a candidate module can import the base without importing the controller,
which imports the candidate. bot_i <-> challenge_controller was a real cycle: registration
silently failed and the desk ran without BOT_I while printing a one-line warning.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Signal:
    strategy_id: str
    strategy_version: str
    timestamp: str
    symbol: str
    side: int                      # +1 long, -1 short
    entry_type: str                # "stop" | "market" | "limit"
    entry_price: float
    stop_price: float
    target_price: float
    expected_holding_minutes: int
    reason_codes: list = field(default_factory=list)
    feature_snapshot: dict = field(default_factory=dict)

    def risk_distance(self) -> float:
        return abs(self.entry_price - self.stop_price)


class Bot:
    """Every candidate implements this. A bot NEVER sends an order."""
    strategy_id = "base"
    strategy_version = "0"
    symbol = ""
    stage = "IDEA"
    prior_expectancy_R = 0.0        # from backtest -- a PRIOR, not a promise
    prior_n = 0
    risk_override = None            # new bots start smaller than experimental
    shadow = False                  # True = records full signals, NEVER sends an order
    # ---- specialist declaration. What this bot was DESIGNED for. A priori, not fitted:
    # a fade bot avoids strong trends by construction, not because it lost money in one.
    playbook = ""                   # BREAKOUT | REVERSION | CONTINUATION
    primary: set = set()
    secondary: set = set()
    avoids: set = set()

    def _no(self, reason: str) -> None:
        """Record WHY there was no trade. 'NO SIGNAL' is not a diagnosis: a bot that is
        silent because its window is shut and one that is silent because its data is
        missing look identical, and only one of them is working correctly."""
        self.no_signal_reason = reason
        return None

    def generate_signal(self, ctx) -> Signal | None:
        raise NotImplementedError

    def manage_position(self, position, ctx) -> str:
        """Return "hold" or "close". Default: broker stop/target does the work."""
        return "hold"


