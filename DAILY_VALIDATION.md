# DAILY VALIDATION — 2026-08-20

## DESK STATUS: **AMBER**

**VALID TRADES: 0 / 30**


## Faults

_none_

## Execution

- controller cycles logged today: **631**
- cycle spacing: median 60s, max 60s (within schedule)
- last cycle: 60s ago
- signals 11, attempts 11, fills 6, rejections 5, closes 6

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| market_state_attached_pct | 0.0%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 98.1%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 19658
- `OUTSIDE_WINDOW` × 15270
- `FIRST_BREAK_ALREADY_OCCURRED` × 4002
- `NO_BREAKOUT` × 2460
- `CORRELATION_CAP` × 1926
- `NO_SETUP` × 1640
- `EVENT_BLACKOUT` × 1273
- `OUTRANKED` × 963
- `UNMAPPED` × 898
- `STOP_TOO_TIGHT` × 2

**UNMAPPED reasons exist** — a decision the validator cannot count. Add the pattern to `desk_events.REASON_PATTERNS`.

## Learning

- lessons stored: None%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — market_state_attached_pct at 0.0%. Infrastructure before strategy.
