# DAILY VALIDATION — 2026-09-05

## DESK STATUS: **RED**

**VALID TRADES: 2 / 30**


## Faults

- **RED** WRONG ACCOUNT 1514487471

## Execution

- controller cycles logged today: **893**
- cycle spacing: median 30s, max 60s (within schedule)
- last cycle: 15s ago
- signals 13, attempts 13, fills 8, rejections 5, closes 8

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| lessons_stored_pct | 100.0% |
| market_state_attached_pct | 15.4%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 97.4%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 51019
- `OUTSIDE_WINDOW` × 48496
- `FIRST_BREAK_ALREADY_OCCURRED` × 11607
- `NO_BREAKOUT` × 8428
- `EVENT_BLACKOUT` × 5290
- `NO_SETUP` × 4139
- `UNMAPPED` × 3613
- `CORRELATION_CAP` × 1926
- `ALREADY_TRADED_TODAY` × 1918
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
