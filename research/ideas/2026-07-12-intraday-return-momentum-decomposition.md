---
type: research-idea
title: "Intraday return momentum decomposition"
status: rejected      # 2026-07-12 OVERNIGHT_MOMENTUM_REVIEW: mechanism replicates (0.40 > 0.20 > -0.22 ordering) but below gauntlet bar at 8-ETF breadth; CFD-dead on financing
created: 2026-07-12
source: "survey_triage #1 (Barardehi/Bogousslavsky/Muravyev RFS 2026, mechanism corrected)"
tags: [research, idea]
---
# Intraday return momentum decomposition

## Hypothesis
Rank/condition on the PAST INTRADAY (open-to-close) return component — per RFS 2026 the momentum-bearing signal (overnight-formed portfolios show NO momentum; the survey's original framing was backwards). Test on liquid ETFs, daily OHLC, Alpaca-side; CFD variant must include financing (Part C lesson: financing kills slow strategies on CFDs).

## Graveyard check (do FIRST)
- [ ] Not already rejected in `FINDINGS.md` / `HUNT_LOG.md` /
      [[02-Strategy-Research/Rejected Ideas|Rejected Ideas]]

## A-priori parameters (write BEFORE testing — no grid-search-then-report-best)
- signal: trailing 12m sum of open-to-close returns (canonical lookback, no tuning)
- universe: the 8 Part-C ETFs; long top-half vs flat (long-only Alpaca variant reported first)
- costs: 3bps/side + the CFD financing scenario as a mandatory second table

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
