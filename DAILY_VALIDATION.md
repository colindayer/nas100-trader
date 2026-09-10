# DAILY VALIDATION — 2026-09-10

## DESK STATUS: **RED**

**VALID TRADES: 4 / 30**


## Faults

- **RED** WRONG ACCOUNT 1514487471

## Execution

- controller cycles logged today: **1171**
- cycle spacing: median 60s, max 64s (within schedule)
- last cycle: 59s ago
- signals 15, attempts 15, fills 10, rejections 5, closes 10

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| lessons_stored_pct | 100.0% |
| market_state_attached_pct | 26.7%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 97.4%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 59395
- `OUTSIDE_WINDOW` × 56254
- `FIRST_BREAK_ALREADY_OCCURRED` × 13929
- `NO_BREAKOUT` × 9525
- `EVENT_BLACKOUT` × 6190
- `NO_SETUP` × 4891
- `UNMAPPED` × 4115
- `ALREADY_TRADED_TODAY` × 2544
- `CORRELATION_CAP` × 1926
- `OUTRANKED` × 963
- `STOP_TOO_TIGHT` × 4

**UNMAPPED reasons exist** — a decision the validator cannot count. Add the pattern to `desk_events.REASON_PATTERNS`.

## Learning

- lessons stored: 100.0%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — WRONG ACCOUNT 1514487471
