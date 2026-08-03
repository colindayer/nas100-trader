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

        # ---- ACCOUNT BINDING. Every Guardian percentage is divided by INITIAL_BALANCE, so a
        # config written for one account silently mis-scales every limit on another. Measured on
        # 2026-08-03: guardian.env carried Pepperstone's 50000 while connected to FTMO at 100000,
        # which reported total_drawdown_pct -100.0 and, worse, meant the TOTAL-loss stop could not
        # fire until equity fell to 45000 -- a real drawdown of 55%. The daily stop was
        # simultaneously over-tight. Both directions wrong from one stale constant.
        #
        # Fail CLOSED when the configured balance does not match the connected account.
        try:
            import MetaTrader5 as _mt5
            _a = _mt5.account_info()
        except Exception:
            _a = None
        if _a is not None:
            _bal = float(getattr(_a, "balance", 0.0) or 0.0)
            _cfg_bal = float(getattr(cfg, "INITIAL_BALANCE", 0.0) or 0.0)
            if _bal > 0 and _cfg_bal > 0 and abs(_bal - _cfg_bal) / _bal > 0.02:
                return False, {"reason": "GUARDIAN_BALANCE_MISMATCH",
                               "account": getattr(_a, "login", None),
                               "account_balance": _bal, "config_initial_balance": _cfg_bal,
                               "hint": "config/guardian.env INITIAL_BALANCE does not match the "
                                       "connected account; every drawdown limit would be "
                                       "mis-scaled. Update it for THIS account before trading."}
        # V-04 fix: baselines come from PERSISTED safety state, not from current equity.
        # Defaulting to current equity made the baseline follow the account down, so realised
        # drawdown always read ~0 and the daily/total stop could never trigger.
        if day_start_equity is None or hwm is None:
            try:
                from .safety_state import guardian_baselines
                p_dse, p_hwm = guardian_baselines(equity=snap.equity)
            except Exception:
                p_dse = p_hwm = None
            day_start_equity = day_start_equity if day_start_equity is not None else p_dse
            hwm = hwm if hwm is not None else p_hwm
        dse = day_start_equity if day_start_equity is not None else snap.balance
        h = hwm if hwm is not None else max(snap.balance, snap.equity)
        dec = evaluate(snap, cfg, dse, h, consecutive_losses, trades_today, cooldown_until,
                       proposed_risk_pct=proposed_risk_pct)
        return bool(dec.get("allow_new_entries")), dec
    except Exception as e:
        return False, {"reason": "GUARDIAN_ERROR", "error": str(e)[:120]}
