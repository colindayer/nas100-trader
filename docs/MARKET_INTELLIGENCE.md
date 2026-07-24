# MARKET_INTELLIGENCE

The Market Intelligence Engine observes markets and produces **evidence**. It never trades.

## Flow
```
Market data (MT5 authoritative; TradingView advisory)
        ↓
market_intel/state.py         classify: trend, volatility, liquidity, session, kill zones,
                              PDH/PDL/PWH/PWL, opening range, ATR+percentile, sweeps, FVG,
                              order blocks, BOS/structure, VWAP, S/R
        ↓
market_intel/engine.py        pre-event reports (direction=None) · post-Actual opportunities
        ↓
Opportunity Registry → Belief Graph → Guardian → Promotion Pipeline
        → Shadow → Limited Demo → Full Demo → Live
```

## Hard guarantees
- No module in `market_intel/` references `order_send`, `place_order`, or `TRADE_ACTION_DEAL`
  (`test_package_cannot_place_orders`).
- Opportunities are generated **only after** an official `actual` exists (`test_no_opportunity_before_actual`).
- Pre-event reports carry `direction: None` (`test_pre_event_report_has_no_direction`).
- Missing Belief Graph or Guardian ⇒ `RESEARCH_ONLY`, never an implicit allow
  (`test_pipeline_fails_closed_when_components_unwired`).

## Running
```
py -m market_intel.dashboard --symbols EURUSD,XAUUSD,NAS100     # text
py -m market_intel.web --port 8787                              # browser
```
