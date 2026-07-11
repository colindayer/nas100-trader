# PART C — New family candidate: canonical TSMOM (12m sign, monthly, 8 ETFs)

_Moskowitz/Ooi/Pedersen rule, pre-registered: 252d lookback, sign, monthly rebalance, equal weight, lagged execution. 2005-2026. Turnover ~1.8x gross/yr. No parameter search. Correlation to current book (S1+S5 QQQ): **n/a**._

| account | CAGR | Sharpe | IS | OOS | MaxDD | 6-split OOS Sharpe |
|---|---|---|---|---|---|---|
| ETF account (no financing) | +5.3% | 0.45 | 0.51 | 0.39 | -36.6% | 0.42 0.39 0.54 0.48 0.57 0.68 |
| CFD account (3 bps/day financing) | -2.0% | -0.08 | 0.07 | -0.31 | -61.8% | -0.29 -0.31 -0.14 -0.18 -0.08 0.06 |

## Prop / execution compatibility
- Holding period ~1 month -> overnight+weekend holds every week. FundedNext Stellar
  permits holding; FTMO regular does not (Swing account required). Constraint, not blocker.
- Broker-side stops: TSMOM has no natural stop (sign-flip exit). A catastrophe SL
  (e.g. 10%) is attachable without changing the rule -- same pattern as OVN.
- **CFD financing is the decisive economics**: see table -- on CFDs the strategy pays
  ~7.5%/yr on gross notional, which consumes most/all of the edge. Viable on the
  Alpaca ETF side (cash account, longs unfinanced); NOT viable as a Pepperstone CFD book.

## Verdict: **NEEDS_MORE_EVIDENCE** (ETF-account variant only; CFD variant REJECTED on financing)
