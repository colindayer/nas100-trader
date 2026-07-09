---
type: experiment
id: EXP-20260710-01
title: "DIX regime filter on 3 pillars"
status: queued          # queued -> running -> gauntlet -> rejected | validated
created: 2026-07-10
idea: "2026-07-10-dark-pool-dix-regime-filter"
paper: "zarattini-2024-orb-stocks-in-play"
datasets: "qqq_hourly_7y.csv, SqueezeMetrics DIX CSV"
script: ""              # set when the test script exists in research/experiments/
reviewer: ""            # REQUIRED (different model/person than author) before 'validated'
author: "research-ai"
tags: [research, experiment]
---
# EXP-20260710-01 - DIX regime filter on 3 pillars

## Origin
- Idea:  [[2026-07-10-dark-pool-dix-regime-filter]]
- Paper: [[zarattini-2024-orb-stocks-in-play]]

## Hypothesis
_One falsifiable sentence._

## Success criteria (write BEFORE running -- the gauntlet, non-negotiable)
- [ ] IS/OOS walk-forward, costs ON
- [ ] OOS Sharpe > 0.5 and IS Sharpe > 0
- [ ] OOS max DD > -35%, >= 30 OOS trades
- [ ] |corr to QQQ weekly| < 0.3
- [ ] Positive/flat in the 2022 bear sub-period
- [ ] 6/6 IS/OOS split robustness (edge_hunt --sweep style)
- [ ] Extra criteria specific to this experiment:

## Datasets
- qqq_hourly_7y.csv
- SqueezeMetrics DIX CSV

## Backtests (fill as they run)
| date | script | split | IS Sharpe | OOS Sharpe | OOS DD | trades | corr | verdict |
|---|---|---|---|---|---|---|---|---|

## Verdict
_rejected (default) -> one line to FINDINGS/HUNT_LOG; validated -> reviewer sign-off
below, then human decision. NOTHING integrates during the 30-day stats window._

## Reviewer sign-off
- reviewer: (must differ from author)
- date:
- notes:

## Links
[[Research Index]] | [[02-Strategy-Research/Gauntlet|Gauntlet]] | [[00 Dashboard]]
