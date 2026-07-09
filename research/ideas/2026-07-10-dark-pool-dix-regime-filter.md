---
type: research-idea
title: "Dark-pool DIX regime filter"
status: idea            # idea -> experiment -> gauntlet -> rejected | validated
created: 2026-07-10
source: "12-Ideas parking lot"
tags: [research, idea]
---
# Dark-pool DIX regime filter

## Hypothesis
_One sentence: what edge, on what instrument, why should it exist (mechanism)?_

## Graveyard check (do FIRST)
- [ ] Not already rejected in `FINDINGS.md` / `HUNT_LOG.md` /
      [[02-Strategy-Research/Rejected Ideas|Rejected Ideas]]

## A-priori parameters (write BEFORE testing — no grid-search-then-report-best)
-

## Gauntlet plan
- [ ] Standalone script in `research/experiments/` (never the live path)
- [ ] IS/OOS walk-forward, costs ON
- [ ] OOS Sharpe > 0.5 and IS Sharpe > 0, OOS DD > -35%, >= 30 trades
- [ ] |corr to QQQ weekly| < 0.3
- [ ] Works in bear sub-period (2022)
- [ ] Robust across 6/6 IS/OOS splits (`edge_hunt.py --sweep`)

## Result
_status + one honest paragraph. If rejected: one line to FINDINGS/HUNT_LOG and stop._

## Links
[[Research Index]] | [[02-Strategy-Research/Gauntlet|Gauntlet]] | [[00 Dashboard]]
