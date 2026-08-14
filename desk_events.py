"""STRUCTURED EVENTS — machine-readable evidence for every decision, including no-trade.

    data/logs/events.jsonl        append-only, one JSON object per decision

WHY NO-TRADE IS EVIDENCE
  On 2026-08-14 BOT_A refused a re-test and the desk could not answer whether it had ever seen
  the break live, because the only record was a human-readable line printed after the fact.
  A desk that records only its trades cannot distinguish "no opportunity existed" from "the
  desk failed to observe the opportunity" -- and that distinction is the whole validation
  mission.

REASON CODES ARE THE POINT
  Free text explains to a human. A code lets the validator COUNT: how many sessions were missed
  for lack of funding, how many for regime mismatch, how many are unexplained. Text is kept
  alongside because a code alone loses the number that made it true.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "data" / "logs" / "events.jsonl"

# ---- no-trade reason codes. Derived from the controller's own English, so the two can never
# disagree: if a new reason appears without a code it surfaces as UNMAPPED rather than hiding.
REASON_PATTERNS = (
    ("outside window",              "OUTSIDE_WINDOW"),
    ("first break already",         "FIRST_BREAK_ALREADY_OCCURRED"),
    ("no break:",                   "NO_BREAKOUT"),
    ("no sweep",                    "NO_SWEEP"),
    ("already traded today",        "ALREADY_TRADED_TODAY"),
    ("structurally wrong",          "REGIME_MISMATCH"),
    ("group at",                    "CORRELATION_CAP"),
    ("total cap",                   "TOTAL_RISK_CAP"),
    ("outranked",                   "OUTRANKED"),
    ("RISK MANAGER veto",           "RISK_VETO"),
    ("challenge veto",              "RISK_VETO"),
    ("inside the noise",            "STOP_INSIDE_NOISE"),
    ("too tight vs spread",         "STOP_TOO_TIGHT"),
    ("DATA_INTEGRITY",              "MISSING_MARKET_STATE"),
    ("event blackout",              "EVENT_BLACKOUT"),
    ("BLOCKED --",                  "ATTEMPT_CAP"),
    ("no M1 data",                  "DATA_GAP"),
    ("insufficient M1",             "DATA_GAP"),
    ("data gap",                    "DATA_GAP"),
    ("bars, need",                  "DATA_GAP"),
    ("no D1 ATR",                   "DATA_GAP"),
    ("not a pullback",              "NO_SETUP"),
    ("sigma from VWAP",             "NO_SETUP"),
    ("swept and reclaimed",         "NO_SETUP"),
    ("no rejection",                "NO_SETUP"),
    ("no retest",                   "NO_SETUP"),
    ("displacement",                "NO_SETUP"),
    ("notional",                    "NOTIONAL_CAP"),
    ("below min",                   "VOLUME_BELOW_MIN"),
)


def reason_code(text: str) -> str:
    """Map the controller's own wording to a countable code. UNMAPPED is deliberate: a reason
    with no code must be visible, not silently bucketed into OTHER."""
    if not text:
        return "UNSPECIFIED"
    low = text.lower()
    for pat, code in REASON_PATTERNS:
        if pat.lower() in low:
            return code
    return "UNMAPPED"


def emit(component: str, event: str, **fields):
    """Append one immutable event. Never raises -- an observability failure must not stop
    trading, so it degrades to a stderr note and the desk continues."""
    try:
        EVENTS.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
               "component": component, "event": event, **fields}
        with EVENTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception as e:                      # observability is auxiliary, never critical
        print(f"  [events] could not write: {e}", file=sys.stderr)


def no_trade(bot, desk_now, reason: str, funded: bool, **extra):
    """The event that 2026-08-14 needed and did not have.

    `beyond_level` is the decisive field: it records whether price was ACTUALLY observed past
    the trigger during an evaluation. Without it, a refusal and a miss look identical.
    """
    emit("challenge_controller", "NO_TRADE",
         bot=getattr(bot, "strategy_id", str(bot)),
         playbook=getattr(bot, "playbook", None),
         symbol=getattr(bot, "symbol", None),
         ts_london=str(desk_now),
         funded=funded,
         reason_code=reason_code(reason),
         reason=reason,
         **extra)


def fallback(what: str, preferred: str, used: str, why: str):
    """Every substitution of a preferred source is an EVENT, never a silent swap.

    Five defects on this desk were silent fallbacks: the anchor, the clock, the offset
    rounding, the Dukascopy cache, the encoding. Each reported healthy numbers while wrong.
    """
    emit("desk", "FALLBACK", what=what, preferred=preferred, used=used, why=why)


def read(day: str | None = None) -> list:
    if not EVENTS.exists():
        return []
    out = []
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if day is None or r.get("ts_utc", "").startswith(day):
            out.append(r)
    return out
