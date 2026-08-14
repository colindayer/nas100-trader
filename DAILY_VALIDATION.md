# DAILY VALIDATION — 2026-08-14

## DESK STATUS: **AMBER**

**VALID TRADES: 0 / 30**


## Faults

- AMBER host clock 16 min from broker

## Execution

- controller cycles logged today: **856**
- cycle spacing: median 60s, max 64s (within schedule)
- last cycle: 30s ago
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

- `REGIME_MISMATCH` × 2568
- `CORRELATION_CAP` × 1712
- `OUTSIDE_WINDOW` × 957
- `OUTRANKED` × 856
- `FIRST_BREAK_ALREADY_OCCURRED` × 422
- `NO_BREAKOUT` × 153

## Learning

- lessons stored: None%
- voided (instrumentation faults, never losses): 6

## Code updates

- up to date

## Recommendation

**FIX PROVEN DEFECT** — market_state_attached_pct at 0.0%. Infrastructure before strategy.
