# DESK_SYSTEM_MAP — what you actually own

Release candidate, TASK-0005 + TASK-0004 integrated. Classification is by **proved call path**,
not by a file existing. "DISCONNECTED" means nothing in the live path imports or invokes it.

## PRODUCTION — in the live decision or protection path

| Component | Input | Output | Consumer | Proof |
|---|---|---|---|---|
| **MT5 / FTMO terminal** | broker | ticks, bars, positions, orders, deals, account | everything | `terminal64.exe`, account 1514166963 bound in `guardian.env` |
| **ChallengeController** | MT5 + ledger | orders, events, logs | broker, ledger | `ChallengeController` task, 1 min |
| **Clock / feed safety** | ticks, host UTC, persisted offset | one of six states | entry gate only | `MS.clock_state()` at `:1358` |
| **Market State** | MT5 bars | ~39 field families × 4 timeframes | opportunity classification, bots, ledger | `MS.compute()` at `:1415` |
| **Macro Context** | MT5 bars of proxy symbols | cross-asset labels; calendar NULL | `utility()` scoring | `MC.compute()` at `:1416` |
| **CIO** | opportunities, candidates, beliefs, open exposure | per-bot allocation | sizing | `DESK.allocate()` at `:1525` |
| **Risk Manager** | challenge anchors, open risk | veto / risk % | order construction | `ChallengeState.veto()` at `:1575` |
| **Bots / specialists** | market state, M1 bars, clock | Signal or no-signal reason | CIO | `generate_signal()` at `:1506` |
| **Stop geometry** | signal, ATR, spread, excursion | approve / widen / reject | sizing | `stop_geometry()` at `:1563` |
| **Exposure gate** | live + sent-this-cycle | allow / block | `order_send` | `exposure_gate()` at `:1637` |
| **Broker SL/TP** | order request | broker-side protection | broker | set at `:1662`; no `TRADE_ACTION_SLTP` anywhere |
| **Time exits** | host clock + ledger | position close | broker | `time_exits()` at `:1347` |
| **Reconciliation** | broker deals | net, R, MFE, MAE | ledger, Brain | `reconcile()` at `:1348` |
| **Trade ledger** | intents + closes | append-only JSONL | Brain, anchors, exits | `data/challenge/trades.jsonl` |
| **Posterior learning** | closed non-void trades | beliefs | CIO utility | `trading_brain.belief()` |
| **Daily review** | ledger + MT5 + events | `DAILY_HEAD_TRADER.md` | human | `HeadTraderReview`, 21:00 London |
| **DeskOrchestrator** | events, ledger, reports | health, evidence push | human, GitHub | `DeskOrchestrator`, 15 min |
| **Scheduled tasks** | Windows Task Scheduler | three enabled desk tasks | — | verified on the VPS 2026-08-15 |

## SHADOW — recorded, never executed

| Component | Status |
|---|---|
| **Shadow system** (`shadows.py`) | Predicates over the stored state, evaluated at `:1608`, written with the intent. Influences nothing. Inherits the parent's real fill; `None ≠ False`. |
| **Shadow-only bots** | None registered. The mechanism is live; the population is empty. |

## RESEARCH — real, useful, outside the live path

| Component | Status |
|---|---|
| **Weekly review** (`trading_brain --weekly`) | Implemented, **manual only** — no scheduled task invokes it |
| **Backtests / sweeps** | ~140 root modules imported by nothing in the live path |
| **TradingView MCP** | Mac-side, CDP port 9222, requires the desktop app and a human. Cannot run on the VPS. Never in the live loop |
| **Obsidian bridge** | Write-only changelog publisher; no retrieval exists; no research library present |
| **OpenClaw / Qwen** | One-shot reviewer transport for the agent bridge. No filesystem, shell, git or MT5. No trading authority |

## DISCONNECTED — present in the repository, imported by zero live modules

`execution_safety/` (27 files) · `market_intel/` (16) · `broker/` (4) · `risk/` (5, imported by
nothing at all) · `dashboard/` (3) · `live_trader.py` + `mt5_broker.py` (the legacy stack) ·
`optionsdx/` (6.2 GB of unused data)

## RETIRED — deliberately, on evidence

| Component | Reason |
|---|---|
| **BOT_I** | 7.3 trades/year measured; unfalsifiable on any horizon that matters. Class kept as the record |
| **Legacy `Nas100Bot-*` tasks** | All five Disabled since 2026-07-26, pointing at a different folder. Magic 770001 absent from the book |
| **`fresh_m1_data` preflight check** | Structurally incapable — compared a stale bar to a stale tick |
| **`and False` skew branch** | Dead duplicate of the measurement `HOST_CLOCK_UNTRUSTED` now acts on |

## Connections that do NOT exist

- Nothing reads the Obsidian vault. The bridge is one-way.
- TradingView cannot reach MT5, the VPS, or any order path.
- No LLM — Claude, Qwen, z.ai — can place, modify or cancel an order.
- The legacy stack shares the terminal but not the desk: every desk filter matches magic 990001,
  so a 770001 position would be invisible to `reconcile`, `time_exits`, `desk_exposure` and
  preflight. Currently moot — those tasks are disabled and no such position exists.
- `ChallengeState.open_risk_pct` reads the ledger only, with no broker cross-check.
