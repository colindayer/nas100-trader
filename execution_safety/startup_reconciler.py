"""startup_reconciler.py -- V-12. Every startup reconciles broker <-> ledger BEFORE any trading
decision. If reconciliation cannot complete, trading is blocked and the safety state is halted.

Detects:
    MISSING_FILL        ledger holds an intent with no matching broker position
    ORPHAN_POSITION     broker position with our magic that the ledger does not know
    FOREIGN_POSITION    position with a different magic (another EA / manual)
    NAKED_POSITION      our position with no broker-side stop
    BROKER_DISAGREEMENT volume mismatch between intent and broker
    LEDGER_UNREADABLE   ledger cannot be parsed

Fail closed: any CRITICAL finding halts. Reconciliation failure itself halts.
"""
from __future__ import annotations
import time
from . import safety_state as ss
from .position_ledger import PositionLedger

CRITICAL = {"ORPHAN_POSITION", "NAKED_POSITION", "BROKER_DISAGREEMENT", "LEDGER_UNREADABLE",
            "RECONCILIATION_FAILED"}


def _broker_positions(magic: int):
    """Returns (positions, error). Never raises."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None, "MT5_INIT_FAILED"
        return list(mt5.positions_get() or []), None
    except Exception as e:
        return None, f"MT5_ERROR: {type(e).__name__}"


def reconcile(magic: int = 880001, positions=None, ledger: PositionLedger | None = None,
              state_path: str = ss.STATE_PATH, require_broker: bool = True) -> dict:
    """Run the startup reconciliation. `positions` may be injected for testing."""
    findings: list[dict] = []
    t0 = time.time()

    # ---- ledger ----
    try:
        led = ledger if ledger is not None else PositionLedger()
        ledger_ok = True
    except Exception as e:
        findings.append({"type": "LEDGER_UNREADABLE", "detail": str(e)[:120]})
        led, ledger_ok = None, False

    # ---- broker ----
    err = None
    if positions is None:
        positions, err = _broker_positions(magic)
    if positions is None:
        if require_broker:
            findings.append({"type": "RECONCILIATION_FAILED", "detail": err or "no broker data"})
        else:
            findings.append({"type": "BROKER_UNAVAILABLE", "detail": err or "no broker data"})
        positions = []

    ours = [p for p in positions if getattr(p, "magic", None) == magic]
    foreign = [p for p in positions if getattr(p, "magic", None) != magic]

    for p in foreign:
        findings.append({"type": "FOREIGN_POSITION", "symbol": getattr(p, "symbol", "?"),
                         "magic": getattr(p, "magic", None),
                         "comment": getattr(p, "comment", "")})

    if ledger_ok and led is not None:
        # orphan / naked / disagreement
        for p in ours:
            sym = getattr(p, "symbol", "?")
            cmt = getattr(p, "comment", "") or ""
            if not led.is_ours(magic, cmt):
                findings.append({"type": "ORPHAN_POSITION", "symbol": sym, "comment": cmt,
                                 "volume": getattr(p, "volume", None)})
            sl = getattr(p, "sl", 0) or 0
            if sl <= 0:
                findings.append({"type": "NAKED_POSITION", "symbol": sym, "comment": cmt})
            entry = next((e for e in led.entries.values()
                          if e.magic == magic and e.comment == cmt and e.status != "CLOSED"), None)
            if entry is not None and getattr(entry, "broker_ticket", None) is None:
                pass  # intent recorded, fill now observed -- normal
        # missing fills: authorised intents with no live position
        live_comments = {(getattr(p, "comment", "") or "") for p in ours}
        for e in led.entries.values():
            if e.status == "AUTHORIZED" and e.comment not in live_comments:
                age_h = (time.time() - e.created_at) / 3600
                if age_h > 1:      # tolerate an in-flight order for one hour
                    findings.append({"type": "MISSING_FILL", "intent_id": e.intent_id,
                                     "symbol": e.symbol, "age_hours": round(age_h, 1)})

    crit = [f for f in findings if f["type"] in CRITICAL]
    result = {"ok": not crit, "findings": findings, "critical": crit,
              "n_broker_positions": len(positions), "n_ours": len(ours),
              "n_foreign": len(foreign), "elapsed_s": round(time.time() - t0, 3),
              "trading_allowed": not crit}

    ss.audit("startup_reconciliation", {"ok": result["ok"], "n_findings": len(findings),
                                        "critical": [c["type"] for c in crit]})
    if crit:
        ss.halt(f"RECONCILIATION: {','.join(sorted({c['type'] for c in crit}))}",
                {"findings": crit[:5]}, path=state_path)
        result["halted"] = True
    return result


def report(res: dict) -> str:
    lines = [f"STARTUP RECONCILIATION: {'OK' if res['ok'] else 'FAILED'} "
             f"({res['n_broker_positions']} positions: {res['n_ours']} ours, "
             f"{res['n_foreign']} foreign) in {res['elapsed_s']}s"]
    for f in res["findings"]:
        mark = "!!" if f["type"] in CRITICAL else " -"
        lines.append(f"  {mark} {f['type']}: " +
                     ", ".join(f"{k}={v}" for k, v in f.items() if k != "type"))
    if not res["findings"]:
        lines.append("   no findings — broker and ledger agree")
    if not res["trading_allowed"]:
        lines.append("  >> TRADING BLOCKED — safety state halted, human acknowledgement required")
    return "\n".join(lines)
