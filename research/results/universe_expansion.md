# PART A — Universe expansion (S1 + S5 unchanged, 11 tickers, 2021+)

_Alpaca extended-hours hourly (same lineage as the validated basket). 3 bps/side. No per-ticker tuning. IS/OOS = first/second half. best_yr_share = best year's P&L / total (concentration flag >0.8)._

| ticker | strat | CAGR | Sharpe | IS | OOS | MaxDD | trades | bestYr share | corr to QQQ-twin | CFD? | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| QQQ | S1 | +3.1% | 0.58 | 0.34 | 0.81 | -7.4% | 96 | 60% |  | US100 | KEEP |
| QQQ | S5 | +11.1% | 1.10 | 0.58 | 1.65 | -9.7% | 268 | 26% |  | US100 | KEEP |
| SPY | S1 | +3.0% | 0.68 | -0.07 | 1.27 | -5.8% | 59 | 43% | 0.13 | US500 | REJECT (economics) |
| SPY | S5 | +6.4% | 0.76 | 0.38 | 1.18 | -11.0% | 212 | 39% | 0.31 | US500 | KEEP |
| IWM | S1 | +1.0% | 0.21 | -0.80 | 0.94 | -12.3% | 99 | 167% | 0.10 | US2000(?) | REJECT (economics) |
| IWM | S5 | +1.7% | 0.22 | 0.15 | 0.30 | -16.4% | 299 | 67% | 0.29 | US2000(?) | REJECT (economics) |
| DIA | S1 | +2.1% | 0.52 | -0.28 | 1.16 | -8.0% | 54 | 34% | 0.00 | US30 | REJECT (economics) |
| DIA | S5 | +6.5% | 0.81 | 0.57 | 1.07 | -6.4% | 185 | 30% | 0.17 | US30 | KEEP |
| SMH | S1 | +3.9% | 0.63 | 0.54 | 0.70 | -7.2% | 131 | 47% | 0.08 | none | KEEP |
| SMH | S5 | +27.1% | 2.04 | 1.36 | 2.70 | -7.7% | 376 | 12% | 0.31 | none | KEEP |
| SOXX | S1 | +3.7% | 0.64 | 0.21 | 0.98 | -7.4% | 110 | 83% | 0.11 | none | REJECT (economics) |
| SOXX | S5 | +16.5% | 1.41 | 1.48 | 1.33 | -9.3% | 344 | 21% | 0.28 | none | KEEP |
| XLK | S1 | +5.0% | 0.88 | 0.67 | 1.07 | -4.3% | 94 | 31% | 0.30 | none | KEEP |
| XLK | S5 | +7.3% | 0.72 | 0.40 | 1.05 | -12.6% | 311 | 27% | 0.50 | none | DUPLICATE (corr) |
| XLF | S1 | +0.9% | 0.21 | 0.13 | 0.27 | -9.0% | 92 | 74% | 0.07 | none | REJECT (economics) |
| XLF | S5 | +6.6% | 0.76 | 0.42 | 1.12 | -10.6% | 222 | 34% | 0.14 | none | KEEP |
| XLE | S1 | +1.1% | 0.21 | 0.59 | -0.30 | -10.4% | 129 | 111% | -0.01 | none | REJECT (economics) |
| XLE | S5 | +13.9% | 1.28 | 1.20 | 1.39 | -10.4% | 306 | 24% | 0.03 | none | KEEP |
| GLD | S1 | +3.2% | 0.67 | 0.08 | 1.06 | -5.3% | 68 | 47% | -0.01 | XAUUSD | KEEP |
| GLD | S5 | +9.9% | 1.09 | -0.13 | 2.04 | -11.8% | 212 | 49% | 0.05 | XAUUSD | REJECT (economics) |
| TLT | S1 | -2.5% | -0.83 | -0.48 | -1.20 | -13.2% | 46 |  | -0.01 | none | REJECT (economics) |
| TLT | S5 | -4.2% | -0.49 | -0.83 | -0.13 | -21.7% | 225 |  | -0.00 | none | REJECT (economics) |

**Pooled (keepers, equal weight): Sharpe 2.32, 11 streams: ['S1_QQQ', 'S5_QQQ', 'S5_SPY', 'S5_DIA', 'S1_SMH', 'S5_SMH', 'S5_SOXX', 'S1_XLK', 'S5_XLF', 'S5_XLE', 'S1_GLD']**

Mean correlation of non-QQQ streams to their QQQ twin: **0.14** — values near/above 0.5 = mostly duplicated Nasdaq exposure, not independent opportunity.

## Overall verdict: **CANDIDATE_FOR_INDEPENDENT_REVIEW**
11 of 22 streams keep (S5 travels well: SPY/DIA/SMH/SOXX/XLF/XLE; S1 only QQQ/SMH/XLK/GLD).
Pooled keeper Sharpe 2.32 with mean cross-correlation 0.14 to the QQQ twins — genuinely
independent opportunity, NOT duplicated Nasdaq beta. Rejected: TLT (both), IWM (both),
XLE-S1/SOXX-S1/IWM-S1 (period concentration >80%), XLK-S5 (corr 0.50 duplicate).
Caveats for the reviewer: 2021+ sample only (~5.5y); several streams show OOS>IS
(recent-period tilt); CFD mapping exists only for QQQ/SPY/DIA/GLD — the rest are
Alpaca-only; per-instrument S5_SMH 2.04 warrants the look-ahead battery from the
EXP-20260711-01 review protocol before anything ships.
