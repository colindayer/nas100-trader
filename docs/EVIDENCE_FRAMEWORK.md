# EVIDENCE_FRAMEWORK — what must be true before live trading is discussed

| requirement | threshold | why |
|--|--|--|
| Minimum trade count | **100 closed demo trades** | matches `LIVE_APPROVED` (`min_demo_trades=100`) |
| Minimum operating days | **60 calendar days** | must span rollovers, reboots, weekends, DST |
| Maximum tolerated incidents | **0 critical, ≤3 non-critical** | critical = orphan, naked fill, duplicate, governance bypass |
| Maximum unexplained executions | **0** | one unexplained order is the incident that started all this |
| Required reconciliation rate | **100% clean startups** | any failure blocks trading by design |
| Required stop verification rate | **100%** | `stop_verified` true on every fill, no exceptions |
| Required deployment consistency | **100% `--verify` COMPLETE** and `--scan-executors` CLEAN | mixed versions caused hours of false debugging |
| Required healthcheck history | **≥60 days, 0 critical failures** | logged, not remembered |
| Research belief | **≥ 0.60** (unchanged) | governance bar, enforced in code |
| Operational belief | **≥ 0.85** | execution proven, not assumed |
| Exit reconciliation | **implemented and proven** | currently absent — `exit_verified` is permanently False |

**Any single unmet row blocks live trading.** These are conjunctive, not a score.
