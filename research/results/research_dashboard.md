# Research Dashboard
_Auto-generated 2026-07-10 10:39. Do not edit — regenerate with `python scripts/research/research_dashboard.py`._

## Summary

| Metric | Count |
|---|---|
| Papers imported | 1 |
| Ideas | 1 |
| Experiments queued | 4 |
| Experiments running | 0 |
| Experiments validated | 0 |
| Experiments rejected | 0 |
| Hunt log entries | 288 |
| Hunt PASS | 27 |
| Hunt FAIL | 261 |
| Velocity (30d) | 6 new items |

## Pipeline Status

```
  Papers (1)
    v
  Ideas (1)
    v
  Queued (4) -> Running (0)
    v                        v
  Validated (0)  <- Gauntlet ->  Rejected (0)
    v
  HUNT_LOG: 27 PASS / 261 FAIL
```

## Queued Experiments

| ID | Title | Status | Created |
|---|---|---|---|
| EXP-20260710-01 | DIX regime filter on 3 pillars | queued | 2026-07-10 |
| TASK-20260710-01 | Review DIX experiment result table | running | 2026-07-10 |
| TASK-20260710-02 | Summarize Moskowitz TSMOM paper | running | 2026-07-10 |
| TASK-20260710-03 | Nightly ops digest wiring | running | 2026-07-10 |

## Ideas

| Title | Status | Created |
|---|---|---|
| [Dark-pool DIX regime filter](research/ideas/2026-07-10-dark-pool-dix-regime-filter.md) | idea | 2026-07-10 |

## Imported Papers

| Title | Authors | Year | Status |
|---|---|---|---|
| [Zarattini 2024 ORB Stocks in Play](research/papers/zarattini-2024-orb-stocks-in-play.md) | Zarattini, Aziz, Barbon | 2024 | unread |

### Hunt Log Failures

| Edge | OOS Sharpe | Verdict |
|---|---|---|
| turn_of_month | 0.38 | **FAIL** |
| pairs_xle_xop | -0.14 | **FAIL** |
| pairs_ko_pep | -0.29 | **FAIL** |
| pairs_gld_tlt | -0.36 | **FAIL** |
| rsi2_spy | 0.55 | **FAIL** |
| tsmom_spy | 0.58 | **FAIL** |
| short_reversal_qqq | -0.19 | **FAIL** |
| crypto_weekend | -0.92 | **FAIL** |
| defensive_rotation | -0.26 | **FAIL** |
| sector_momentum | -0.04 | **FAIL** |
| turn_of_month | 0.43 | **FAIL** |
| pairs_gld_gdx | 0.44 | **FAIL** |
| pairs_xle_xop | -0.09 | **FAIL** |
| pairs_ko_pep | -0.28 | **FAIL** |
| pairs_gld_tlt | -0.4 | **FAIL** |
| rsi2_spy | 0.5 | **FAIL** |
| tsmom_spy | 0.45 | **FAIL** |
| short_reversal_qqq | -0.21 | **FAIL** |
| crypto_weekend | -0.85 | **FAIL** |
| defensive_rotation | -0.35 | **FAIL** |
_...and 241 more in HUNT_LOG.md_

## Recent AI Work (14 days)

| Date | Role | Change | Commits |
|---|---|---|---|
| 2026-07-10 | Lead Engineer / Claude Code | AI_OPERATING_SYSTEM.md + this changelog created (process docs only, no Python) | (this commit) |
| 2026-07-10 | Lead Engineer / Claude Code | Monitoring-phase health check: no confirmed issue → no code change | none |
| 2026-07-10 | Lead Engineer / Claude Code | CURRENT_PROJECT_STATE.md onboarding snapshot | 535579f |
| 2026-07-09 | Lead Engineer / Claude Code | 30-day monitoring plan | 24eb4b9 |
| 2026-07-09 | Lead Engineer / Claude Code | **Parity fixes:** get_bars DAYS→BARS unit bug (Alpaca), 30→1200-bar lookbacks (E... | 236abe3, 419da99 |
| 2026-07-09 | Lead Engineer / Claude Code | Production readiness review (88 demo / 55 funded) + fixes: startup heal, Alpaca ... | fd0ff25, 62b90c6 |
| 2026-07-09 | Lead Engineer / Claude Code | Startup fix: unterminated string L135 + args-before-parse (lock block) — repaire... | (folded into fd0ff25) |
| 2026-07-08/09 | Research / Fable | risk/ mode package (dormant), prop optimizer, trade forensics (NO_REAL_TRADES_RO... | 42676fc + docs |
| 2026-07-02 | Obsidian Bridge / automated | Merge PR #9: DIX gate rejected + self-updating updater | f8947d7 |
| 2026-07-04 | Obsidian Bridge / automated | Add Virtue-of-Complexity (Kelly/Malamud/Zhou JF 2024) timing test | eb27d68 |
| 2026-07-03 | Obsidian Bridge / automated | Merge PR #10: Virtue-of-Complexity timing test | 4a60f62 |
| 2026-07-04 | Obsidian Bridge / automated | Demote hourly session-complete Telegram ping to once-daily heartbeat | ae0ea20 |
| 2026-07-04 | Obsidian Bridge / automated | Merge PR #11: once-daily Telegram heartbeat | 5c97a4b |
| 2026-07-05 | Obsidian Bridge / automated | Add diag_live.py — dump live MT5 bar ET hours to explain zero signals | a13a560 |
| 2026-07-06 | Obsidian Bridge / automated | Fix: force UTF-8 stdout so scheduled Windows runs don't crash on emoji | ae148e3 |
| 2026-07-06 | Obsidian Bridge / automated | Hardening: ASCII logs, broker-specific sweep universe, status.py, per-venue M... | 27a9911 |
| 2026-07-06 | Obsidian Bridge / automated | Add S5 ORB watchdog (canary alert if 9:00 ET bar missing in window) + fix set... | e06255d |
| 2026-07-06 | Obsidian Bridge / automated | Trim MT5 sweep universe to broker-available CFDs (per-broker); log venue fixes | 86d4221 |
| 2026-07-06 | Obsidian Bridge / automated | Merge origin/main into work branch (resolve venue-fix overlap) | 567f91a |
| 2026-07-06 | Obsidian Bridge / automated | Merge PR #12: venue-reliability FINDINGS log + sweep reconciliation | 029867c |

## Research Statistics

- **Total edges tested:** 288
- **Pass rate:** 9.4%
- **Rejection rate:** 90.6%
- _History: ~30 ideas in, ~2 survived long-term (the pipeline's job is to say no)_

---
_Back: [[Research Index]] | [[00 Dashboard]]_