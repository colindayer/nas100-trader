# DAILY VALIDATION — 2026-09-02

## DESK STATUS: **RED**

**VALID TRADES: 0 / 30**


## Faults

- **RED** WRONG ACCOUNT 1514487471

## Execution

- controller cycles logged today: **506**
- cycle spacing: median 30s, max 60s (within schedule)
- last cycle: 13s ago
- signals 11, attempts 11, fills 6, rejections 5, closes 6

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| market_state_attached_pct | 0.0%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 97.9%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 32280
- `OUTSIDE_WINDOW` × 25759
- `FIRST_BREAK_ALREADY_OCCURRED` × 6232
- `NO_BREAKOUT` × 3273
- `EVENT_BLACKOUT` × 2293
- `NO_SETUP` × 1961
- `CORRELATION_CAP` × 1926
- `UNMAPPED` × 1571
- `OUTRANKED` × 963
- `STOP_TOO_TIGHT` × 2

**UNMAPPED reasons exist** — a decision the validator cannot count. Add the pattern to `desk_events.REASON_PATTERNS`.

## Learning

- lessons stored: None%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — WRONG ACCOUNT 1514487471
