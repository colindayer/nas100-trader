"""gsr_strategy.py -- Gold/Silver-Ratio mean-reversion (Gupta 2026, replicated TR-a921975d8eef2571)
as a first-class EXECUTABLE strategy. It EMITS Signal objects for the gate; it NEVER calls a broker.
Whether an emitted signal ever becomes an order is decided entirely by authorize() -> the gate.
Frozen params = the replicated paper params. Status is governed by its StrategyContract, NOT by code.

[STATUS: UNUSED - no runner invokes this. Kept for traceability only.]
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .gate import Signal

STRATEGY_ID, VERSION = "gsr_meanrev", "v1"
W = int(252 * 7); Z = 1.25; HOLD = 15; COST_BPS = 10


def latest_signal(gold_silver: pd.DataFrame, equity=50000) -> Signal | None:
    """gold_silver: daily DataFrame with columns gold, silver (most recent last). Returns a Signal to
    go long silver iff the frozen GSR condition fires on the latest CLOSED bar, else None. Causal:
    z-score is lagged one day."""
    d = gold_silver.dropna()
    if len(d) < W + 11:
        return None
    gsr = d.gold / d.silver
    z = (gsr - gsr.rolling(W).mean()) / gsr.rolling(W).std()
    z_lag = z.shift(1).iloc[-1]
    confirm = gsr.iloc[-1] <= 0.98 * gsr.rolling(10).max().iloc[-1]
    if not (z_lag > Z and confirm):
        return None
    price = float(d.silver.iloc[-1])
    stop = round(price * 0.90, 4)        # protective stop (10% below); broker-side, plausible (<15%)
    return Signal(signal_id=f"gsr-{d.index[-1].date()}", strategy_id=STRATEGY_ID,
                  strategy_version=VERSION, symbol="XAGUSD", direction=1,
                  entry=price, stop_loss=stop, take_profit=None)
