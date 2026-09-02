# DAILY VALIDATION — 2026-09-02

## DESK STATUS: **RED**

**VALID TRADES: 1 / 30**


## Faults

- **RED** WRONG ACCOUNT 1514487471

## Execution

- controller cycles logged today: **1753**
- cycle spacing: median 30s, max 60s (within schedule)
- last cycle: 58s ago
- signals 12, attempts 12, fills 7, rejections 5, closes 7

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| lessons_stored_pct | 100.0% |
| market_state_attached_pct | 8.3%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 98.2%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 36021
- `OUTSIDE_WINDOW` × 27799
- `FIRST_BREAK_ALREADY_OCCURRED` × 7730
- `NO_BREAKOUT` × 4453
- `EVENT_BLACKOUT` × 2888
- `NO_SETUP` × 1997
- `CORRELATION_CAP` × 1926
- `UNMAPPED` × 1571
- `OUTRANKED` × 963
- `ALREADY_TRADED_TODAY` × 885
- `STOP_TOO_TIGHT` × 2

**UNMAPPED reasons exist** — a decision the validator cannot count. Add the pattern to `desk_events.REASON_PATTERNS`.

## Learning

- lessons stored: 100.0%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — WRONG ACCOUNT 1514487471
