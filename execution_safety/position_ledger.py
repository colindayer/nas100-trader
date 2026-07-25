"""position_ledger.py -- PHASE 601 Stage 8. One immutable, append-only ledger that joins:
trial -> contract -> inference decision -> order intent -> broker position. Every open broker
position must answer "why does this exist?". A broker position whose (magic, comment) has no ledger
entry is an ORPHAN_POSITION => alert, block all new orders, never assume ownership, require human
classification. Fail closed.
"""
from __future__ import annotations
import json, os, time
from dataclasses import dataclass, asdict, field

LEDGER = "registry/position_ledger.jsonl"


@dataclass
class LedgerEntry:
    intent_id: str
    trial_ids: list
    strategy_id: str
    strategy_version: str
    decision_id: str
    symbol: str
    magic: int
    comment: str
    created_at: float
    broker_ticket: int | None = None
    status: str = "AUTHORIZED"          # AUTHORIZED -> FILLED -> CLOSED
    history: list = field(default_factory=list)


class PositionLedger:
    def __init__(self, path=LEDGER):
        self.path = path
        self.entries: dict[str, LedgerEntry] = {}
        self.malformed: list = []
        self._load()

    def _load(self):
        """V-06: a torn line no longer raises inside the order path. Malformed lines are recorded
        as defects and skipped, so the ledger degrades rather than aborting a submission."""
        self.malformed = []
        if not os.path.exists(self.path):
            return
        for n, line in enumerate(open(self.path), 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                self.entries[d["intent_id"]] = LedgerEntry(**d)
            except Exception as e:
                self.malformed.append({"line": n, "error": type(e).__name__})

    def _append(self, e: LedgerEntry):
        """V-06: single-writer discipline. Concurrent runners can no longer interleave a torn line."""
        from .safety_state import acquire, release
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        lp = acquire(self.path)
        try:
            with open(self.path, "a") as f:             # append-only => immutable audit trail
                f.write(json.dumps(asdict(e)) + "\n")
                f.flush(); os.fsync(f.fileno())
        finally:
            release(lp)

    def record_intent(self, intent: dict, trial_ids: list, decision_id: str) -> LedgerEntry:
        e = LedgerEntry(intent_id=intent["intent_id"], trial_ids=trial_ids,
                        strategy_id=intent["strategy_id"], strategy_version=intent["strategy_version"],
                        decision_id=decision_id, symbol=intent["symbol"], magic=intent["magic_number"],
                        comment=intent["comment"], created_at=intent["created_at"])
        self.entries[e.intent_id] = e; self._append(e)
        return e

    def is_ours(self, magic: int, comment: str) -> bool:
        return any(e.magic == magic and e.comment == comment for e in self.entries.values())


def classify_broker_positions(positions, ledger: PositionLedger, our_magic: int) -> dict:
    """Any broker position not traceable to a ledger entry is an ORPHAN => block everything."""
    orphans = []
    for p in positions:
        magic = getattr(p, "magic", None); comment = getattr(p, "comment", "")
        if magic == our_magic and ledger.is_ours(magic, comment):
            continue
        orphans.append({"symbol": getattr(p, "symbol", "?"), "magic": magic, "comment": comment})
    return {"orphans": orphans, "block_all_orders": bool(orphans),
            "policy": "ORPHAN_POSITION: alert, block new orders, require human classification"
                      if orphans else "clean"}
