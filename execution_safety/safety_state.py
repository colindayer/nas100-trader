"""safety_state.py -- persistent Safety State. Closes VERIFICATION_REPORT V-01, V-02, V-04.

The platform is a SCHEDULED ONE-SHOT, not a long-running supervisor. Every safety control that must
span invocations therefore has to live on disk, not in memory:

    V-01  daily trade count   (was reset every process start -> cap defeated)
    V-02  emergency halt      (was erased every process start -> halt lasted <15 min)
    V-04  guardian baselines  (defaulted to CURRENT equity -> drawdown could never trigger)

Guarantees
  * versioned      every record carries SCHEMA_VERSION; unknown version => fail closed
  * atomic         tmp + os.replace, so a crash mid-write cannot truncate the live file
  * checksummed    payload digest detects corruption; corrupt => fail closed (HALTED)
  * append-only    every transition is also written to an immutable audit log
  * fail closed    ANY read problem yields a halted state, never a permissive one
"""
from __future__ import annotations
import hashlib, json, os, tempfile, time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

SCHEMA_VERSION = 1
STATE_PATH = "registry/safety_state.json"
AUDIT_PATH = "registry/safety_state_audit.jsonl"
LOCK_SUFFIX = ".lock"
BACKUP_SUFFIX = ".bak"
LOCK_STALE_S = 120          # a lock older than this is assumed abandoned (crashed writer)


class StateLocked(RuntimeError):
    """Another process owns the safety state. Fail closed rather than overspend the envelope."""


def _lock_path(path): return path + LOCK_SUFFIX


def acquire(path: str = STATE_PATH, timeout: float = 5.0, owner: str | None = None) -> str:
    """Exclusive advisory lock via O_EXCL. Prevents two scheduled runs from independently
    resetting or overspending the envelope. Stale locks (crashed writer) are reclaimed."""
    lp = _lock_path(path)
    owner = owner or f"pid{os.getpid()}"
    d = os.path.dirname(lp)
    if d:
        os.makedirs(d, exist_ok=True)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"owner": owner, "ts": time.time()}).encode())
            os.close(fd)
            return lp
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(lp)
                if age > LOCK_STALE_S:
                    audit("lock_reclaimed", {"age_s": round(age), "owner": owner})
                    os.unlink(lp)
                    continue
            except FileNotFoundError:
                continue
            if time.time() >= deadline:
                raise StateLocked(f"safety state locked by another process (>{timeout}s)")
            time.sleep(0.05)


def release(lp: str):
    try:
        os.unlink(lp)
    except FileNotFoundError:
        pass


def _utc_day(ts: float | None = None) -> str:
    """UTC day key. Deliberately NOT local time (V-09): the broker/prop day is UTC-anchored."""
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m-%d")


def _digest(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()[:32]


@dataclass
class SafetyState:
    schema_version: int = SCHEMA_VERSION
    day: str = field(default_factory=_utc_day)
    trades_today: int = 0
    halted: bool = False
    halt_reason: str | None = None
    halt_ts: float | None = None
    halt_ack_required: bool = True          # clearing ALWAYS needs an explicit human action
    day_start_equity: float | None = None
    high_water_mark: float | None = None
    last_update: float = field(default_factory=time.time)
    last_intent_id: str | None = None       # idempotency hook for duplicate detection

    def payload(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ audit
ALERT_EVENTS = {"HALT", "HALT_CLEARED", "state_corrupt", "state_checksum_mismatch",
                "state_schema_mismatch", "state_recovered_from_backup", "trade_refused_cap"}


def _alert(event: str, detail: dict):
    """Best-effort notification. NEVER raises and never blocks a state transition:
    a failed alert must not prevent a halt from being recorded."""
    try:
        from market_intel import telegram_notifier as tg
        crit = event in ("HALT", "state_corrupt", "state_checksum_mismatch", "state_schema_mismatch")
        body = f"<b>{event}</b>\n" + "\n".join(f"{k}: {v}" for k, v in list(detail.items())[:6])
        tg.critical(body) if crit else tg.send("critical_error", body)
    except Exception:
        pass


def audit(event: str, detail: dict, path: str | None = None):
    """Immutable record of every critical state transition.
    Path resolves at CALL time (module-level default was previously frozen at import)."""
    path = path or AUDIT_PATH
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"ts": time.time(), "utc": datetime.now(timezone.utc).isoformat(),
                            "event": event, **detail}, default=str) + "\n")
    if event in ALERT_EVENTS:
        _alert(event, detail)


# ------------------------------------------------------------------ io
def save(st: SafetyState, path: str = STATE_PATH) -> SafetyState:
    st.last_update = time.time()
    body = {"payload": st.payload()}
    body["digest"] = _digest(body["payload"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".safety_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(body, f, indent=1)
            f.flush()
            os.fsync(f.fileno())            # survive power loss, not just process death
        if os.path.exists(path):             # keep a recovery copy of the last good state
            try:
                import shutil; shutil.copy2(path, path + BACKUP_SUFFIX)
            except Exception:
                pass
        os.replace(tmp, path)               # atomic
    except Exception:
        try: os.unlink(tmp)
        except Exception: pass
        raise
    return st


def load(path: str = STATE_PATH, equity: float | None = None) -> tuple[SafetyState, list[str]]:
    """Return (state, notes). ANY problem => halted state. Never returns a permissive default."""
    notes: list[str] = []
    if not os.path.exists(path):
        st = SafetyState(day_start_equity=equity, high_water_mark=equity)
        notes.append("no prior state — initialised")
        audit("state_initialised", {"equity": equity})
        return save(st, path), notes

    try:
        body = json.load(open(path))
    except Exception as e:
        bak = path + BACKUP_SUFFIX
        if os.path.exists(bak):              # try the recovery copy before failing closed
            try:
                body = json.load(open(bak))
                notes.append("primary state unreadable — RECOVERED FROM BACKUP")
                audit("state_recovered_from_backup", {"error": str(e)[:80]})
            except Exception:
                body = None
        else:
            body = None
        if body is None:
            st = SafetyState(halted=True, halt_reason=f"STATE_UNREADABLE: {type(e).__name__}",
                             halt_ts=time.time())
            notes.append("state file unreadable and no usable backup — FAIL CLOSED (halted)")
            audit("state_corrupt", {"error": str(e)[:120], "action": "halted"})
            return st, notes

    payload = body.get("payload", {})
    if body.get("digest") != _digest(payload):
        st = SafetyState(halted=True, halt_reason="STATE_CHECKSUM_MISMATCH", halt_ts=time.time())
        notes.append("checksum mismatch — FAIL CLOSED (halted)")
        audit("state_checksum_mismatch", {"action": "halted"})
        return st, notes

    ver = payload.get("schema_version")
    if ver != SCHEMA_VERSION:
        st = SafetyState(halted=True, halt_reason=f"STATE_SCHEMA_{ver}_EXPECTED_{SCHEMA_VERSION}",
                         halt_ts=time.time())
        notes.append(f"schema {ver} != {SCHEMA_VERSION} — FAIL CLOSED (halted)")
        audit("state_schema_mismatch", {"found": ver, "expected": SCHEMA_VERSION})
        return st, notes

    try:
        st = SafetyState(**payload)
    except Exception as e:
        st = SafetyState(halted=True, halt_reason=f"STATE_FIELDS_INVALID: {type(e).__name__}",
                         halt_ts=time.time())
        notes.append("state fields invalid — FAIL CLOSED (halted)")
        audit("state_fields_invalid", {"error": str(e)[:120]})
        return st, notes

    # ---- UTC day rollover: reset the counter, NEVER the halt ----
    today = _utc_day()
    if st.day != today:
        audit("day_rollover", {"from": st.day, "to": today, "trades_prev_day": st.trades_today,
                               "halt_preserved": st.halted})
        st.day = today
        st.trades_today = 0
        st.day_start_equity = equity if equity is not None else st.day_start_equity
        notes.append(f"UTC day rollover -> counter reset (halt preserved: {st.halted})")
        save(st, path)

    if equity is not None:
        if st.high_water_mark is None or equity > st.high_water_mark:
            st.high_water_mark = equity
            save(st, path)
        if st.day_start_equity is None:
            st.day_start_equity = equity
            save(st, path)

    if st.halted:
        notes.append(f"HALTED: {st.halt_reason} (since {st.halt_ts})")
    return st, notes


# ------------------------------------------------------------------ transitions
class EnvelopeExhausted(RuntimeError):
    """The daily slot could not be claimed. The caller MUST NOT proceed to submit."""


def record_trade(intent_id: str | None = None, path: str = STATE_PATH,
                 max_per_day: int | None = None) -> SafetyState:
    """ATOMIC compare-and-increment under lock.

    The cap is enforced HERE, not by the caller. A separate allow()-then-record() sequence is a
    time-of-check/time-of-use race: two schedulers can both pass allow() before either records.
    Passing max_per_day makes claiming a slot a single atomic operation.
    Raises EnvelopeExhausted if no slot is available.
    """
    lp = acquire(path)
    try:
        st, _ = load(path)
        if intent_id and st.last_intent_id == intent_id:
            audit("trade_duplicate_ignored", {"intent_id": intent_id})
            return st                                  # idempotent
        if st.halted:
            raise EnvelopeExhausted(f"HALTED: {st.halt_reason}")
        if max_per_day is not None and st.trades_today >= max_per_day:
            audit("trade_refused_cap", {"trades_today": st.trades_today, "cap": max_per_day,
                                        "intent_id": intent_id})
            raise EnvelopeExhausted(f"DAILY_TRADE_LIMIT {st.trades_today}/{max_per_day}")
        st.trades_today += 1
        st.last_intent_id = intent_id
        audit("trade_recorded", {"trades_today": st.trades_today, "intent_id": intent_id})
        return save(st, path)
    finally:
        release(lp)


def halt(reason: str, detail: dict | None = None, path: str = STATE_PATH) -> SafetyState:
    st, _ = load(path)
    if not st.halted:
        st.halted = True
        st.halt_reason = reason
        st.halt_ts = time.time()
        audit("HALT", {"reason": reason, **(detail or {})})
    return save(st, path)


def clear_halt(actor: str, note: str = "", path: str = STATE_PATH) -> SafetyState:
    """Explicit human acknowledgement. There is no automatic un-halt anywhere in the system."""
    if not actor:
        raise ValueError("clear_halt requires an actor — halts are never cleared automatically")
    st, _ = load(path)
    audit("HALT_CLEARED", {"actor": actor, "note": note, "prior_reason": st.halt_reason})
    st.halted = False
    st.halt_reason = None
    st.halt_ts = None
    return save(st, path)


def update_equity(equity: float, path: str = STATE_PATH) -> SafetyState:
    st, _ = load(path, equity=equity)
    return save(st, path)


def guardian_baselines(equity: float | None = None, path: str = STATE_PATH) -> tuple[float | None, float | None]:
    """(day_start_equity, high_water_mark) — persisted, so drawdown does not reset on restart."""
    st, _ = load(path, equity=equity)
    return st.day_start_equity, st.high_water_mark
