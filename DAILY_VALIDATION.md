# DAILY VALIDATION — 2026-09-09

## DESK STATUS: **RED**

**VALID TRADES: 3 / 30**


## Faults

- **RED** WRONG ACCOUNT 1514487471

## Execution

- controller cycles logged today: **1396**
- cycle spacing: median 60s, max 63s (within schedule)
- last cycle: 58s ago
- signals 14, attempts 14, fills 9, rejections 5, closes 9

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| lessons_stored_pct | 100.0% |
| market_state_attached_pct | 21.4%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 97.3%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 55747
- `OUTSIDE_WINDOW` × 53024
- `FIRST_BREAK_ALREADY_OCCURRED` × 12787
- `NO_BREAKOUT` × 8957
- `EVENT_BLACKOUT` × 5740
- `NO_SETUP` × 4635
- `UNMAPPED` × 4115
- `ALREADY_TRADED_TODAY` × 2111
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
