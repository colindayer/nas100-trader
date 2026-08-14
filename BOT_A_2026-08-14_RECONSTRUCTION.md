# BOT_A — 2026-08-14 06:45–06:55 London — RECONSTRUCTION

## VERDICT: **E. IMPOSSIBLE TO DETERMINE — INSUFFICIENT HISTORICAL INSTRUMENTATION**

Persistent controller logging was added at commit `c524a09` and first ran at
**08:00:01 UTC (09:00 London)** — roughly **two hours after** the event. No artifact of any
kind exists for 06:45–06:55.

## Evidence available, item by item

| # | Question | Answer | Source |
|---|---|---|---|
| 1 | Exact cycle timestamps 06:45–06:55 | **UNKNOWN** | log begins 08:00:01 UTC |
| 2 | Did each cycle complete? | **UNKNOWN** individually. Aggregate only: `NumberOfMissedRuns = 0`, `LastTaskResult = 0`, uptime since 2026-07-20, no shutdown events. The task was firing; whether each *process* succeeded is not recorded. | `Get-ScheduledTaskInfo`, `Win32_OperatingSystem` |
| 3 | BOT_A funding status per cycle | **UNKNOWN at 06:51.** At 09:00 BOT_A was funded (XAUUSD `WEAK_TREND` = primary for BREAKOUT). Regime at 06:51 is not recorded. | log 09:00 |
| 4 | `no_signal_reason` per cycle | **UNKNOWN** before 09:00 | — |
| 5 | XAUUSD M1 OHLC 06:45–06:55 | Retrievable from MT5 *now*, but it cannot establish what the controller **observed** | MT5 history |
| 6 | Tick history | Not retained by the desk | — |
| 7 | Breakout level | **UNKNOWN.** Derived per cycle from the 90-min pre-06:30 range and never persisted unless a signal fired. | — |
| 8 | First cross timestamp | **06:51 London**, asserted by the guard at 09:00 | log 09:00 |
| 9 | Was price beyond the level during any evaluation? | **UNKNOWN** — the decisive question, and precisely what was not recorded | — |
| 10 | Would a valid signal have existed absent the guard? | **UNDETERMINABLE** — depends on (9) | — |
| 11 | Classification | **E** | — |

## The hypothesis, and its actual status

The controller samples ~once per minute; each cycle takes 10–30s (state for four symbols), so
real spacing is 60–90s against a 60s bar. Entry tests the **live tick** (`ask >= level`); the
first-break guard tests **closed bars**. A break that begins and retraces between two samples
would therefore be unreachable — and on the following cycle the closed bar makes the guard say
"already happened".

**This remains a HYPOTHESIS.** It is architecturally *possible*. It is not demonstrated for
06:51. Three explanations remain equally consistent with the evidence:

- **B. Sampling race** — price crossed and retraced between observations.
- **C. CIO did not fund BOT_A at 06:51** — gold's regime may have differed from 09:00.
- **A. Correctly rejected** — e.g. `stop_geometry` refused, or the range failed its own filter.

Nothing available distinguishes them.

## Decision

**No change to BOT_A entry timing.** Weakening "do not chase" to recover one historical trade,
on a hypothesis that cannot be tested against that trade, is exactly the failure mode this desk
exists to avoid.

## Instrumentation added so the next occurrence is decisive

`data/logs/events.jsonl` now records, every cycle, for every bot:
`level`, `bid/ask`, `beyond_level` (boolean), `funded`, `reason_code`, plus cycle latency and
the gap since the previous cycle.

When the next first-break is refused, the record will show whether price was **ever observed
beyond the level while the bot was funded**. That proves or kills the sampling race outright.

If proven, the patch and its required tests are pre-specified in `PATCHES.md`.
