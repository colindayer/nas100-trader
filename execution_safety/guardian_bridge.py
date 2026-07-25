"""guardian_bridge.py -- PHASE 601 gap closure. Calls the REAL prop_risk_guardian against a live
MT5 snapshot. FAIL CLOSED: guardian missing, MT5 unreadable, or any exception => do NOT allow.
"""
from __future__ import annotations
import os


def guardian_ok(day_start_equity=None, hwm=None, consecutive_losses=0, trades_today=0,
                cooldown_until=None, proposed_risk_pct=0.0, config=None) -> tuple[bool, dict]:
    """Returns (allow, detail). Never returns True on an error path."""
    try:
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)
        for cand in (here, os.path.join(root, "scripts"), root, os.getcwd(),
                     os.path.join(os.getcwd(), "scripts"),
                     os.path.join(os.getcwd(), "execution_safety")):
            if cand and cand not in sys.path and os.path.isdir(cand):
                sys.path.insert(0, cand)
        from prop_risk_guardian import Config, mt5_snapshot, evaluate
    except Exception as e:
        return False, {"reason": "GUARDIAN_UNAVAILABLE", "error": str(e)[:160],
                       "hint": "place prop_risk_guardian.py in execution_safety\\ or scripts\\ "
                               "and config/guardian.env alongside"}
    try:
        cfg = Config.load(config or os.environ.get("GUARDIAN_CONFIG", "config/guardian.env"))
        snap = mt5_snapshot(cfg)
        if snap is None or not getattr(snap, "ok", False):
            return False, {"reason": "GUARDIAN_SNAPSHOT_BAD"}
        dse = day_start_equity if day_start_equity is not None else snap.balance
        h = hwm if hwm is not None else max(snap.balance, snap.equity)
        dec = evaluate(snap, cfg, dse, h, consecutive_losses, trades_today, cooldown_until,
                       proposed_risk_pct=proposed_risk_pct)
        return bool(dec.get("allow_new_entries")), dec
    except Exception as e:
        return False, {"reason": "GUARDIAN_ERROR", "error": str(e)[:120]}
