# DAILY VALIDATION — 2026-09-11

## DESK STATUS: **RED**

**VALID TRADES: 5 / 30**


## Faults

- **RED** WRONG ACCOUNT 1514487471

## Execution

- controller cycles logged today: **841**
- cycle spacing: median 60s, max 63s (within schedule)
- last cycle: 60s ago
- signals 16, attempts 16, fills 11, rejections 5, closes 11

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| lessons_stored_pct | 100.0% |
| market_state_attached_pct | 31.2%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 97.4%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 62698
- `OUTSIDE_WINDOW` × 59624
- `FIRST_BREAK_ALREADY_OCCURRED` × 14990
- `NO_BREAKOUT` × 9714
- `EVENT_BLACKOUT` × 6395
- `NO_SETUP` × 5073
- `UNMAPPED` × 4355
- `ALREADY_TRADED_TODAY` × 2801
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
