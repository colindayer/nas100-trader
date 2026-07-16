# C3 — Production Execution Architecture (Design)

**Status: DESIGN ONLY. No production code changed by this document.**
Scope: a universal exit/lifecycle architecture guaranteeing every live position is managed
safely across Python crashes, VPS death, MT5 disconnects, network failure, and restarts.
(Naming note: research-lab's `ARCHITECTURE_C3.md` covers *research* C3 — quant modules and
scaled experiments. This document is the *production* C3. They share only the promotion
boundary.)

---

## Part 1 — Architecture review: weaknesses in the current design

Grounded in `live_trader.py` (1,149 lines), `mt5_broker.py`, `LIVE_SAFETY_AUDIT.md`:

| # | Weakness | Evidence | Consequence |
|---|----------|----------|-------------|
| W1 | **Exit logic is per-strategy and inline.** Each `run_s1..s5/run_btc/run_overnight/run_btctrend` implements its own exit handling inside the strategy function. | `live_trader.py:316–800` | Every new strategy re-implements lifecycle safety; every bug is repeated per strategy; no single place to audit "is this position managed?" |
| W2 | **Not every position has broker-side protection.** BTCTREND holds a vol-target position with **no SL** (state-machine rebalance only). | `LIVE_SAFETY_AUDIT.md` §1 (🟡 MED) | If the bot/VPS dies mid-trend-reversal, the position runs unmanaged — exactly the BTC give-back incident class. |
| W3 | **State is scattered JSON with no journal.** `logs/btc_state.json`, `btc_trend_state.json`, `risk_state_*.json` — write-in-place, no schema/version, no write-ahead intent. | `live_trader.py:139,669` | A crash between order-send and state-write leaves internal state contradicting the broker; restart trusts stale JSON. |
| W4 | **No systematic restart reconciliation.** Only BTC has a reconcile step; others assume their state file is truth. `protect_positions.py` exists but is a *manual one-time* cleanup, not a startup phase. | `protect_positions.py` header | Orphan positions (broker has it, state doesn't — or vice versa) are undetected except for BTC. |
| W5 | **Time-based exits depend on the bot being alive.** S3 5-day exit, OVN next-morning close are bot-side only. | audit §1 | Bot down at the exit moment → position overstays; only capped by the (wide) catastrophe SL where one exists. |
| W6 | **Scheduler-coupled lifecycle.** Positions are managed only when the hourly/daily run happens to execute; there is no continuous management loop or watchdog between runs. | `run_btc` "run hourly" comment | Invalidation between runs is invisible; a whole bar of adverse movement passes unmanaged. |
| W7 | **No liveness signal.** Nothing detects "process died" vs "process idle"; the evidence bridge is read-only, not a watchdog. | scripts/ops | Failures discovered by humans reading dashboards, not by the system. |
| W8 | **`live_trader.py.bak` and lock files as process control.** File locks handle double-start, but there is no supervised restart or crash-loop backoff. | `live_trader.py:67–87` | After a crash, nothing restarts management automatically. |

What is already *right* and must be preserved: broker-side brackets at entry for S1/S2/S4/S5/SWEEP/BTC (the audit's green rows), the per-broker abstraction (`Broker` base), the evidence bridge (read-only), and the file-lock discipline.

---

## Part 2 — C3 architecture: modules, responsibilities, interfaces

```
                       PRODUCTION (VPS)                                RESEARCH (Mac)
┌─────────────────────────────────────────────────────────┐   ┌─────────────────────────┐
│  Strategy plugins (entry + invalidation + exit params)  │   │ research-lab            │
│        │ EntryIntent / ExitPolicy (data only)           │   │  - exit optimization    │
│        ▼                                                │   │  - validation, WF, MC   │
│  ┌───────────────┐   ┌──────────────────────────────┐   │   │  - objective ranking    │
│  │ Exit Manager  │◄──│ State Journal (SQLite WAL)   │   │   └───────────┬─────────────┘
│  │ (lifecycle)   │   │ intents, positions, versions │   │               │
│  └──────┬────────┘   └──────────────────────────────┘   │      ExitPolicy JSON
│         ▼                                                │   (human-promoted, signed
│  ┌───────────────┐   ┌──────────────────────────────┐   │    config — never code)
│  │ Broker Gateway│   │ Reconciler (startup + cont.) │   │               │
│  │ (MT5 adapter) │◄──│ broker truth vs journal      │   │◄──────────────┘
│  └──────┬────────┘   └──────────────────────────────┘   │
│         ▼                                                │
│  MT5 terminal ── broker-side SL/TP = ALWAYS-ON floor    │
│                                                          │
│  Watchdog (separate process): heartbeat, restart, alert │
└─────────────────────────────────────────────────────────┘
```

Modules (each small, single-responsibility; target ≤300 lines apiece):

| Module | Responsibility | Explicitly NOT responsible for |
|--------|----------------|-------------------------------|
| `exit_manager` | The only component that closes/modifies positions in normal operation. Runs the lifecycle FSM per position. | entries, sizing decisions, strategy logic |
| `broker_gateway` | Thin, retrying, idempotent wrapper over `mt5_broker`. Every mutating call takes a client-order-id; safe to repeat. | any decision-making |
| `journal` | SQLite (WAL mode) single source of *internal* state: order intents (written BEFORE send), position records, ExitPolicy versions, lifecycle events. Append-only events + current-state tables. | being trusted over the broker |
| `reconciler` | On startup and every N minutes: broker positions vs journal. Classifies matches/orphans/ghosts; adopts or protects orphans; closes out ghosts from the journal. | closing healthy positions |
| `policy_store` | Loads promoted ExitPolicy JSON per strategy (versioned, checksummed). Refuses to run a strategy without one. | optimization (that's research) |
| `watchdog` | Separate OS process/task: heartbeat file check, process restart with backoff, alert on repeated failure. | trading decisions |
| strategies | Provide `entry_signal()`, `is_invalidated()`, and their promoted ExitPolicy. | order placement, exit execution, state persistence |

**The five-layer exit guarantee** (every position, no exceptions):

1. **Normal exit** — the C2-optimized exit family (ATR target, R-multiple, scale-out, trailing ATR, MA/trend exit, volatility exit), executed bot-side by the Exit Manager.
2. **Invalidation exit** — `is_invalidated()` checked continuously; thesis gone → flat, regardless of P&L.
3. **Emergency broker protection** — broker-side SL (and optional TP) attached **in the same order request as entry** (MT5 supports atomic SL/TP on `ORDER_TYPE_*`), *never optimized*, wide enough to never be the normal exit, tight enough to bound catastrophe (e.g. 2–3× the normal stop distance). If attach-at-entry fails, the position is closed immediately — an unprotected position is a bug, not a state.
4. **Maximum holding period** — `max_bars`/`max_hours` per strategy; enforced bot-side, with the broker-side backstop being the emergency SL plus (where the broker supports it) order expiry.
5. **Fail-safe on doubt** — any state the FSM cannot classify → protect first (ensure broker SL), alert, and freeze new entries for that strategy.

---

## Part 3 — Universal Exit Manager API

Everything below is an interface sketch (signatures + contracts), not implementation.

```python
# ---------- what a STRATEGY provides (and nothing more) ----------
class Strategy(Protocol):
    name: str
    symbol: str
    def entry_signal(self, bars) -> EntryIntent | None: ...
    def is_invalidated(self, bars, position: PositionRecord) -> InvalidationVerdict: ...
    # exit parameters come from the promoted ExitPolicy, not from code

@dataclass(frozen=True)
class EntryIntent:            # pure data; no side effects
    symbol: str; side: str; risk_fraction: float
    thesis: str               # human-readable why (journaled)
    tag: str                  # strategy tag for reconciliation

@dataclass(frozen=True)
class InvalidationVerdict:
    invalidated: bool
    reason: str | None        # "trend gone", "vol regime changed", "structure broken"

# ---------- the promoted, versioned exit configuration ----------
@dataclass(frozen=True)
class ExitPolicy:             # produced by research (C2), promoted by a human, loaded as JSON
    version: str              # content hash + date; journaled with every position
    normal: dict              # {"family": ["atr_stop","rr_target",...], "params": {...}}
    emergency_sl_mult: float  # e.g. 2.5 x normal stop distance -- NEVER optimized
    emergency_tp_mult: float | None
    max_bars: int | None
    max_hours: float | None
    def validate(self) -> list[str]: ...   # non-empty family, emergency > normal, a max hold set

# ---------- the Exit Manager ----------
class ExitManager:
    def __init__(self, gateway: BrokerGateway, journal: Journal, policies: PolicyStore): ...

    def open(self, strategy: Strategy, intent: EntryIntent) -> PositionRecord:
        """Journal intent -> send entry WITH broker SL/TP attached -> journal fill.
        Raises ProtectionError (and flattens) if protection cannot be confirmed."""

    def manage(self, position: PositionRecord, bars) -> LifecycleEvent | None:
        """One tick of the FSM: check invalidation, normal exits, max-hold, trailing
        updates (ratchet broker SL upward as the trailing level moves). Idempotent."""

    def adopt(self, broker_position, policy: ExitPolicy | None) -> PositionRecord:
        """Reconciler hands over an orphan: ensure emergency SL, rebuild FSM state
        from broker data + journal history (or conservative defaults)."""

    def flatten(self, position: PositionRecord, reason: str) -> LifecycleEvent:
        """Close now; retry with escalation; journal outcome."""

# ---------- position lifecycle FSM ----------
# PENDING -> PROTECTED_OPEN -> (MANAGED trailing/partials) -> CLOSING -> CLOSED
#                       └─> ADOPTED (from reconciler) -> MANAGED
# any state on unrecoverable doubt -> PROTECT_AND_FREEZE
@dataclass
class PositionRecord:
    ticket: int; symbol: str; strategy: str; side: str; qty: float
    entry_px: float; opened_at: datetime
    policy_version: str
    fsm_state: str
    broker_sl: float; broker_tp: float | None
    mfe: float; mae: float          # maintained per tick for give-back exits + research
    partials_done: list[str]
```

Interaction rule: **strategies never see the broker; the Exit Manager never computes
signals.** The scheduler calls `strategy.entry_signal()`; on intent it calls
`exit_manager.open()`; thereafter a management loop (every bar or minute, decoupled from
strategy schedules — fixes W6) calls `manage()` for every open position.

Backward compatibility: existing S1–S5 already use broker brackets at entry; they migrate
by (a) extracting their current stop/target settings into ExitPolicy JSON verbatim, and
(b) replacing inline close logic with `is_invalidated()`. Behavior-preserving first, exits
re-optimized later via Part 6 evidence.

---

## Part 4 — Restart / Reconciliation engine

**Principle: the broker is the source of truth for existence; the journal is the source of
truth for intent.** Never assume flat without asking the broker.

Startup sequence (also run periodically as continuous reconciliation, e.g. every 5 min):

```
1. CONNECT     gateway.ensure_connected() with bounded retry/backoff
2. SNAPSHOT    broker_positions = gateway.positions()        (by symbol + magic/tag)
               journal_open    = journal.open_positions()
3. CLASSIFY    for each pair (matched by ticket, else by symbol+tag):
               MATCHED   both sides agree           -> rebuild FSM, resume manage()
               ORPHAN    broker has it, journal not -> exit_manager.adopt():
                           ensure emergency SL NOW (protect first, ask questions later),
                           attribute by tag/magic -> its ExitPolicy; unattributable ->
                           conservative default policy + ALERT + freeze that symbol
               GHOST     journal has it, broker not -> mark closed-by-unknown in journal,
                           reconcile P&L from broker history (deals), ALERT
               DIVERGED  qty/side mismatch          -> protect, ALERT, freeze strategy
4. REPLAY      journal intents in state PENDING (crash between intent and fill):
               query broker history for the client-order-id ->
               filled: promote to position; not found: expire the intent
5. RESUME      management loop starts only after reconciliation completes
```

Journal design (anti-W3): SQLite in WAL mode, one file, tables `intents`, `positions`,
`events` (append-only), `policies`. Every broker mutation is journaled as *intent* before
the call and *outcome* after — write-ahead intent makes step 4 deterministic. No JSON
files hold position state anymore; `risk_state` equity tracking can migrate last.

Crash matrix the design must satisfy:

| Failure | What saves the position |
|---------|------------------------|
| Python crash mid-trade | Broker-side SL/TP (layer 3); watchdog restarts; reconciler resumes management |
| Crash between order-send and journal write | Write-ahead intent + step 4 replay via client-order-id |
| VPS dies entirely | Broker-side SL/TP live at the broker, independent of the VPS |
| MT5 terminal crash | SL/TP are server-side at the broker, not terminal-side; gateway reconnects |
| Network loss | Same as VPS death until reconnect; then reconcile |
| Double process start | Existing lock-file discipline retained + journal is single-writer (WAL) |
| Clock/timezone drift | Max-hold uses broker server time from position open, not local wall clock |

---

## Part 5 — Broker safety architecture

- **Atomic protection at entry**: entry order carries SL (and TP where policy says so) in
  the same `order_send` request. No naked interval, ever. If the broker rejects SL-with-entry
  (symbol config), fallback is: entry → immediate `TRADE_ACTION_SLTP` → verify → else close.
  The *verify* step is mandatory; unverified protection counts as no protection.
- **Emergency ≠ normal**: emergency SL distance is a fixed multiple of the policy's normal
  stop (e.g. 2.5×), set from `ExitPolicy.emergency_sl_mult`, excluded from optimization by
  construction (the research firewall never sees this field as a search dimension).
- **Trailing = ratchet the broker SL**, not a bot-side virtual stop: when the trailing level
  advances, the Exit Manager *moves the broker SL up*. Bot death then preserves the trail's
  last level — profit give-back is bounded even unmanaged (directly addresses the BTC
  incident).
- **Idempotent gateway**: every mutating call carries a deterministic client id
  (`hash(strategy, symbol, intent_ts)`); retries never double-fire. Retcode taxonomy:
  retryable (requote, price-off, no-connection) with capped exponential backoff vs terminal
  (invalid stops, not-enough-money) which journal + alert + freeze.
- **Watchdog** (separate process, e.g. schtasks every minute): checks heartbeat file age;
  stale → restart the trader with backoff; repeated failure → alert (existing alerts.py
  channel). The watchdog never trades — worst case, broker-side stops hold the fort.
- **Kill conditions**: daily-loss breach or reconciler `DIVERGED` → flatten-all mode
  requiring human re-arm (a journal flag, not a code change).

---

## Part 6 — Experimental benchmark (evidence before recommendation)

No exit architecture ships on opinion. The benchmark runs entirely in **research-lab**
(all machinery already exists: exit families, `run_spec`, walk-forward, Monte-Carlo,
deployment objectives, profile ranking).

**Datasets**: BTC daily/hourly and NAS100/QQQ daily/hourly research snapshots (hash-stamped
via `vendors.snapshot`).

**Entry controls** (exits must be compared holding entries fixed): the three C2 archetypes
that mirror production families — trend/momentum (BTCTREND-like), breakout (S1/S5-like),
mean-reversion. Same entries across all exit arms.

**Exit arms** (each = one ExitPolicy candidate; all parameter ranges bounded per C2):

| Arm | Family |
|-----|--------|
| E1 | Fixed SL only |
| E2 | Fixed SL + fixed TP |
| E3 | ATR stop + ATR target |
| E4 | ATR trailing (ratchet) |
| E5 | R-multiple target (1/1.5/2/3R) + ATR stop |
| E6 | Scale-out (partial at 1R, trail rest) |
| E7 | Time exit + fixed SL |
| E8 | Invalidation exit + emergency SL only |
| E9 | Hybrid: ATR stop + break-even + trailing + max-hold (the Part 2 default stack) |

**Protocol** per (dataset × entry × arm): C2 bounded param search → Phase B validation
(walk-forward, bootstrap, Monte-Carlo, permutation, DSR/PBO with the search's config
matrix) → deployment simulation under both objectives → evidence package to the KG.

**Ranking**: PROP_CHALLENGE profile (pass probability, DD-violation probabilities, days to
target — not CAGR) and FUNDED_ACCOUNT profile (Sortino, Calmar, MAR, Recovery Factor,
stability, drawdown). Report the two rankings separately; they are expected to disagree.

**Decision rule**: an exit architecture is recommended for production migration only if it
(a) ranks top-3 under the relevant profile on **both** BTC and NAS100, (b) survives
walk-forward with positive OOS consistency, and (c) its advantage over E1/E2 exceeds the
bootstrap CI noise. Ties → the simpler arm wins.

**Additional required measurement**: MAE/MFE distributions per arm (small exits.py
analytics addition, already on the research roadmap) — quantifies profit give-back, the
incident class that motivated C3.

---

## Part 7 — Implementation roadmap (highest production risk first)

| # | Task | Risk retired | Size | Depends on |
|---|------|--------------|------|-----------|
| R1 | **Broker-side protection for BTCTREND** (the one 🟡 MED naked position): attach a wide emergency SL at rebalance, ratcheted with the trend. Config-level change in the existing state-machine. | W2 — unmanaged live position on VPS death | S | none (do first; days, not weeks) |
| R2 | **Watchdog + heartbeat** (separate process; restart with backoff; alert). | W7/W8 — silent death | S | none |
| R3 | **Journal (SQLite WAL) + write-ahead intents** for new orders; migrate BTC state first (it already reconciles). | W3 — state/broker divergence | M | none |
| R4 | **Reconciler** (startup + periodic): classify MATCHED/ORPHAN/GHOST/DIVERGED, adopt-and-protect orphans. Turns `protect_positions.py` from a manual tool into a startup phase. | W4 — orphans undetected | M | R3 |
| R5 | **Exit Manager skeleton + gateway idempotency**: FSM, `open()` with atomic protection + verify, `manage()` loop decoupled from strategy schedules. | W1/W5/W6 | M/L | R3, R4 |
| R6 | **Migrate strategies behavior-preserving**: current stops/targets → ExitPolicy JSON; inline exit code → `is_invalidated()`. One strategy at a time, S3/OVN (bot-dependent exits) first. | W1/W5 | M | R5 |
| R7 | **Run the Part 6 benchmark in research-lab**; promote winning ExitPolicies per strategy per deployment profile (human sign-off). | evidence gap | M | R5 (can start in parallel — research side) |
| R8 | Trailing-ratchet + give-back exits live, per promoted policies. | BTC-incident class | S | R6, R7 |

Sequencing rationale: R1/R2 are cheap and retire the two failure modes that can lose real
money *today*; the journal/reconciler (R3/R4) are the foundation everything else trusts;
the Exit Manager only becomes the single path (R5/R6) once restart safety exists; exit
*optimization* (R7/R8) is deliberately last — safety before performance.

**Non-goals / anti-overengineering**: no message queues, no microservices, no async
framework, no multi-broker orchestration layer — one supervised Python process, one SQLite
journal, one watchdog task, broker-side stops as the physics-level floor. The whole point
is fewer moving parts than today, not more.
