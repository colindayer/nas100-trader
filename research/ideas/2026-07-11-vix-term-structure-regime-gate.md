---
type: research-idea
title: "VIX term structure regime gate"
status: idea            # idea -> experiment -> gauntlet -> rejected | validated
created: 2026-07-11
source: "MACRO_REGIME_SURVEY rank 1"
tags: [research, idea]
---
# VIX term structure regime gate

## Hypothesis
Gate S1/S4/S5 risk-on when VIX3M/VIX > 1.0 (contango); reduce/pause in backwardation. Mechanism: curve inversion prices immediate stress (Fassas & Hourvouliades, SSRN 3189502). Must beat the EXISTING VIX-level gate incrementally, else reject (they co-move).

## Graveyard check (do FIRST)
- [ ] Not already rejected in `FINDINGS.md` / `HUNT_LOG.md` /
      [[02-Strategy-Research/Rejected Ideas|Rejected Ideas]]

## A-priori parameters (write BEFORE testing — no grid-search-then-report-best)
- ratio = ^VIX3M / ^VIX daily close; threshold 1.0 (canonical, no tuning)
- compare 3 variants ALL reported: level-gate only (current), ratio-gate only, both

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
