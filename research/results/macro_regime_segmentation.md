# PART B — Macro regime segmentation (descriptive, lagged, canonical rules)

_Book = S1+S5 on QQQ 2019-2026 (validated engines, 3 bps). Whole-sample Sharpe 1.40. Every variable lagged 1 day. No threshold search. Breadth: pre-registered REJECT (no survivorship-safe free data)._

| regime (risk-ON rule) | %days ON | Sharpe ON | Sharpe OFF | episodes | verdict |
|---|---|---|---|---|---|
| VIX21ma<20 (existing gate) | 62% | 1.48 | 1.29 | 9 | baseline reference |
| VIX3M/VIX>1 (validated shadow) | 93% | 1.62 | -1.66 | 43 | CANDIDATE (already under forward shadow) |
| DGS2 falling (63d chg<0) | 50% | 1.91 | 0.86 | 45 | NEEDS_MORE_EVIDENCE (segmentation only) |
| DGS10 falling (63d chg<0) | 45% | 1.76 | 1.08 | 43 | NEEDS_MORE_EVIDENCE (segmentation only) |
| curve 10y-2y>0 | 71% | 1.48 | 1.20 | 6 | REJECT (too few episodes) |
| HY OAS < 200d MA | 55% | 1.51 | 1.65 | 16 | REJECT (no incremental value) |
| DXY < 200d MA | 46% | 2.09 | 0.81 | 37 | NEEDS_MORE_EVIDENCE (segmentation only) |
| netliq rising (13w chg>0) | 46% | 1.95 | 0.89 | 16 | NEEDS_MORE_EVIDENCE (segmentation only) |

Rule applied: a variable must (a) have >=8 independent episodes, (b) separate ON/OFF Sharpe by >0.5, (c) beat the whole-sample Sharpe when ON — and even then it is only NEEDS_MORE_EVIDENCE until tested as a gate with incremental value over the existing VIX gates (the EXP-20260711-01 protocol).
