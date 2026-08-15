# DAILY VALIDATION — 2026-08-15

## DESK STATUS: **RED**

**VALID TRADES: 0 / 30**


## Faults

- **RED** controller last cycle 56 min ago -- not firing

## Execution

- controller cycles logged today: **97**
- cycle spacing: median 60s, max 48179s (blind spot risk)
- last cycle: 3359s ago
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

**FIX PROVEN DEFECT** — controller last cycle 56 min ago -- not firing
