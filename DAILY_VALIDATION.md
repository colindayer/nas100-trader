# DAILY VALIDATION — 2026-08-24

## DESK STATUS: **RED**

**VALID TRADES: 0 / 30**


## Faults

- **RED** controller last cycle 2583 min ago -- not firing

## Execution

- controller cycles logged today: **0**
- last cycle: 154979s ago
- signals 11, attempts 11, fills 6, rejections 5, closes 6

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| market_state_attached_pct | 0.0%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 98.3%  **<- FIX INFRASTRUCTURE** |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 27894
- `OUTSIDE_WINDOW` × 19897
- `FIRST_BREAK_ALREADY_OCCURRED` × 6207
- `NO_BREAKOUT` × 2952
- `EVENT_BLACKOUT` × 1993
- `CORRELATION_CAP` × 1926
- `NO_SETUP` × 1640
- `UNMAPPED` × 1090
- `OUTRANKED` × 963
- `STOP_TOO_TIGHT` × 2

**UNMAPPED reasons exist** — a decision the validator cannot count. Add the pattern to `desk_events.REASON_PATTERNS`.

## Learning

- lessons stored: None%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — controller last cycle 2583 min ago -- not firing
