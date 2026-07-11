# OVERNIGHT MOMENTUM REVIEW -- Barardehi/Bogousslavsky/Muravyev mechanism (corrected)

_2026-07-12. The RFS 2026 finding under investigation (as corrected by survey triage):
momentum is carried by past INTRADAY (open-to-close) returns; overnight-formed
portfolios show no momentum. Diagnostic run at ETF level (8 liquid ETFs, 2005-2026,
monthly L/S top4-bot4, 12m trailing signal, lagged, 6 bps rt). Analysis only --
no strategy implemented._

## 1. Do our existing overnight systems already capture it? NO -- different mechanisms
- **OVN** holds QQQ overnight on fixed calendar nights (unconditional; no momentum signal).
- **S1** fades an overnight liquidity sweep intraday (reversal, not momentum).
Neither conditions on trailing intraday-return momentum. The literature effect is
mechanistically distinct from both -- so nothing here invalidates or duplicates
our book. But "not captured" is not the same as "worth capturing" (see below).

## 2. Does the literature add incremental information? YES -- the mechanism REPLICATES
The RFS ordering reproduces exactly at ETF level:

| signal (same engine, same costs) | Sharpe | IS | OOS |
|---|---|---|---|
| **INTRADAY component (RFS)** | **0.40** | 0.17 | 0.68 |
| TOTAL return (classic momentum) | 0.20 | 0.25 | 0.14 |
| OVERNIGHT component | -0.22 | -0.02 | -0.39 |

Intraday-signal > total > overnight -- the paper's core claim survives transplant
to ETFs. This is genuine incremental information over classic momentum signals.

## 3. Does CFD financing destroy the edge? YES -- completely
Monthly-hold financing (~63 bps/month on gross notional): Sharpe **-0.26**.
Same verdict as Part C TSMOM: slow strategies cannot live on Pepperstone CFDs.

## 4. Does ETF implementation change the result? YES -- it starves it
The paper's power comes from cross-sectional breadth (thousands of stocks).
At 8 ETFs the effect is directionally intact but economically thin: 0.40 Sharpe
(below the gauntlet's OOS>0.5 bar), unstable halves (IS 0.17), and the
time-series variant on QQQ alone (0.49) loses to buy-and-hold (0.87).

## Verdict: **REJECT** (as a tradeable idea for this shop)
- CFD side: dead on financing (confirmed empirically).
- ETF side: 0.40 at our available breadth -- below the gauntlet bar; widening
  breadth to hundreds of names is a different business (single-stock momentum
  book), not an increment to this one.
- The mechanism itself is REAL and replicated -- recorded as knowledge, not edge.
  If the shop ever runs a broad single-stock Alpaca book, revisit; the idea note
  is closed with that condition attached.
