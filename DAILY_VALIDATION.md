# DAILY VALIDATION — 2026-09-04

## DESK STATUS: **RED**

**VALID TRADES: 1 / 30**


## Faults

- **RED** WRONG ACCOUNT 1514487471

## Execution

- controller cycles logged today: **1722**
- cycle spacing: median 30s, max 60s (within schedule)
- last cycle: 42s ago
- signals 13, attempts 13, fills 8, rejections 5, closes 7

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 87.5%  **<- FIX INFRASTRUCTURE** |
| fills_with_intent_pct | 100.0% |
| lessons_stored_pct | 100.0% |
| market_state_attached_pct | 15.4%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 97.4%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 49542
- `OUTSIDE_WINDOW` × 45914
- `FIRST_BREAK_ALREADY_OCCURRED` × 11253
- `NO_BREAKOUT` × 7728
- `EVENT_BLACKOUT` × 4995
- `NO_SETUP` × 4139
- `UNMAPPED` × 3376
- `CORRELATION_CAP` × 1926
- `ALREADY_TRADED_TODAY` × 1443
- `OUTRANKED` × 963
- `STOP_TOO_TIGHT` × 3

**UNMAPPED reasons exist** — a decision the validator cannot count. Add the pattern to `desk_events.REASON_PATTERNS`.

## Learning

- lessons stored: 100.0%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — WRONG ACCOUNT 1514487471
