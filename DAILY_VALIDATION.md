# DAILY VALIDATION — 2026-08-16

## DESK STATUS: **RED**

**VALID TRADES: 0 / 30**


## Faults

- **RED** controller last cycle 1241 min ago -- not firing
- **RED** WRONG ACCOUNT 61552095

## Execution

- controller cycles logged today: **0**
- last cycle: 74459s ago
- signals 11, attempts 11, fills 6, rejections 5, closes 6

## Instrumentation completeness (target 100%)

| metric | % |
|---|---|
| exits_reconstructed_pct | 100.0% |
| fills_reconciled_pct | 100.0% |
| fills_with_intent_pct | 100.0% |
| market_state_attached_pct | 0.0%  **<- FIX INFRASTRUCTURE** |
| net_economics_pct | 100.0% |
| no_trade_reasons_coded_pct | 100.0% |
| rejections_explained_pct | 100.0% |

## No-trade summary

- `REGIME_MISMATCH` × 2889
- `CORRELATION_CAP` × 1926
- `OUTSIDE_WINDOW` × 1014
- `OUTRANKED` × 963
- `FIRST_BREAK_ALREADY_OCCURRED` × 422
- `NO_BREAKOUT` × 190

## Learning

- lessons stored: None%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — controller last cycle 1241 min ago -- not firing
