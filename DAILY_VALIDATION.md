# DAILY VALIDATION — 2026-08-18

## DESK STATUS: **AMBER**

**VALID TRADES: 0 / 30**


## Faults

_none_

## Execution

- controller cycles logged today: **796**
- cycle spacing: median 60s, max 60s (within schedule)
- last cycle: 58s ago
- signals 11, attempts 11, fills 6, rejections 5, closes 6

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| market_state_attached_pct | 0.0%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 98.2%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 10546
- `OUTSIDE_WINDOW` × 7892
- `CORRELATION_CAP` × 1926
- `FIRST_BREAK_ALREADY_OCCURRED` × 1760
- `NO_BREAKOUT` × 1688
- `OUTRANKED` × 963
- `NO_SETUP` × 798
- `EVENT_BLACKOUT` × 553
- `UNMAPPED` × 471
- `STOP_TOO_TIGHT` × 1

**UNMAPPED reasons exist** — a decision the validator cannot count. Add the pattern to `desk_events.REASON_PATTERNS`.

## Learning

- lessons stored: None%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — market_state_attached_pct at 0.0%. Infrastructure before strategy.
