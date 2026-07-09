# AI CHANGELOG

_Append-only. Every AI session that changes anything adds a row before stopping.
Format: date | role/model | change | evidence/verification | commits._

| Date | Role / model | Change | Evidence / verification | Commits |
|---|---|---|---|---|
| 2026-07-10 | Lead Engineer / Claude Code | AI_OPERATING_SYSTEM.md + this changelog created (process docs only, no Python) | n/a — documentation | (this commit) |
| 2026-07-10 | Lead Engineer / Claude Code | Monitoring-phase health check: no confirmed issue → no code change | logs clean, tree clean, origin==local | none |
| 2026-07-10 | Lead Engineer / Claude Code | CURRENT_PROJECT_STATE.md onboarding snapshot | built from 6 governance docs + 3 core files | 535579f |
| 2026-07-09 | Lead Engineer / Claude Code | 30-day monitoring plan | doc only | 24eb4b9 |
| 2026-07-09 | Lead Engineer / Claude Code | **Parity fixes:** get_bars DAYS→BARS unit bug (Alpaca), 30→1200-bar lookbacks (EMA50/HighVol starvation on MT5), Alpaca brackets DAY→GTC + LIVE_TRADING_PARITY.md | measured: 2→75 daily closes, HV 0→988 bars; dry-runs asian/orb/sweep clean; **30-day stats window anchors at 236abe3** | 236abe3, 419da99 |
| 2026-07-09 | Lead Engineer / Claude Code | Production readiness review (88 demo / 55 funded) + fixes: startup heal, Alpaca BRACKET/OTO, global crash excepthook, test_order demo guard | py_compile, crash-hook simulation, dry-run exit 0 | fd0ff25, 62b90c6 |
| 2026-07-09 | Lead Engineer / Claude Code | Startup fix: unterminated string L135 + args-before-parse (lock block) — repaired a prior agent's broken uncommitted tree | STARTUP_FIX_REPORT.md; ast/py_compile/--help/dry-run all pass | (folded into fd0ff25) |
| 2026-07-08/09 | Research / Fable | risk/ mode package (dormant), prop optimizer, trade forensics (NO_REAL_TRADES_ROOT_CAUSE, LIVE_TRADE_REVIEW), data-fetch hardening | verified by Reviewer session (AGENT_CHANGE_REVIEW.md) — 2 fatal startup bugs found in its uncommitted tree and fixed | 42676fc + docs |
| ≤2026-07-07 | Lead Engineer / Claude Code | Naked-order fix (broker-side SL/TP everywhere), BTC reconcile, OVN catastrophe stop, emoji-crash fix, timezone fix, VPS git deploy, vault, safety audit | LIVE_SAFETY_AUDIT.md, test_order verification on Pepperstone | see git history 0ce6e24 and earlier |
| 2026-07-02 | Obsidian Bridge / automated | Merge PR #9: DIX gate rejected + self-updating updater | git post-commit hook | f8947d7 |
| 2026-07-04 | Obsidian Bridge / automated | Add Virtue-of-Complexity (Kelly/Malamud/Zhou JF 2024) timing test | git post-commit hook | eb27d68 |
| 2026-07-03 | Obsidian Bridge / automated | Merge PR #10: Virtue-of-Complexity timing test | git post-commit hook | 4a60f62 |
| 2026-07-04 | Obsidian Bridge / automated | Demote hourly session-complete Telegram ping to once-daily heartbeat | git post-commit hook | ae0ea20 |
| 2026-07-04 | Obsidian Bridge / automated | Merge PR #11: once-daily Telegram heartbeat | git post-commit hook | 5c97a4b |
| 2026-07-05 | Obsidian Bridge / automated | Add diag_live.py — dump live MT5 bar ET hours to explain zero signals | git post-commit hook | a13a560 |
| 2026-07-06 | Obsidian Bridge / automated | Fix: force UTF-8 stdout so scheduled Windows runs don't crash on emoji | git post-commit hook | ae148e3 |
| 2026-07-06 | Obsidian Bridge / automated | Hardening: ASCII logs, broker-specific sweep universe, status.py, per-venue M... | git post-commit hook | 27a9911 |
| 2026-07-06 | Obsidian Bridge / automated | Add S5 ORB watchdog (canary alert if 9:00 ET bar missing in window) + fix set... | git post-commit hook | e06255d |
| 2026-07-06 | Obsidian Bridge / automated | Trim MT5 sweep universe to broker-available CFDs (per-broker); log venue fixes | git post-commit hook | 86d4221 |
| 2026-07-06 | Obsidian Bridge / automated | Merge origin/main into work branch (resolve venue-fix overlap) | git post-commit hook | 567f91a |
| 2026-07-06 | Obsidian Bridge / automated | Merge PR #12: venue-reliability FINDINGS log + sweep reconciliation | git post-commit hook | 029867c |
| 2026-07-06 | Obsidian Bridge / automated | Log VERIFIED GREEN venue state (2026-07-06): first live MT5 demo trade placed | git post-commit hook | 1ed1d5d |
| 2026-07-06 | Obsidian Bridge / automated | Merge PR #13: log verified-green venue state | git post-commit hook | ca34a5d |
| 2026-07-07 | Obsidian Bridge / automated | CRITICAL FIX: attach broker-side SL/TP to every live order | git post-commit hook | 607f18a |
| 2026-07-07 | Obsidian Bridge / automated | Add protect_positions.py -- attach protective stop to pre-fix naked positions | git post-commit hook | cd66179 |
| 2026-07-07 | Obsidian Bridge / automated | Add test_order.py -- place one demo order with SL/TP to verify brackets (bypa... | git post-commit hook | 9552d58 |
| 2026-07-07 | Obsidian Bridge / automated | Add LIVE_SAFETY_AUDIT.md — execution safety audit (core book protected; BTC/O... | git post-commit hook | e8e0307 |
| 2026-07-07 | Obsidian Bridge / automated | Docs V2: ARCHITECTURE_V2.md + complete Obsidian vault (13 sections, cross-lin... | git post-commit hook | 19f4346 |
| 2026-07-07 | Obsidian Bridge / automated | Docs: vault consolidation plan + code inventory (143 files) + V1->V2 migratio... | git post-commit hook | 0e48ed8 |
| 2026-07-07 | Obsidian Bridge / automated | Phase 1: flatten Obsidian vault (un-nest vault/vault), remove empty obsidian_... | git post-commit hook | b0dfea5 |
| 2026-07-10 | Obsidian Bridge / automated | Add AI_OPERATING_SYSTEM.md (roles, handoffs, memory, pipelines) + seed AI_CHA... | git post-commit hook | d9677a6 |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian Bridge: generate vault/auto/ knowledge base from repo data | git post-commit hook | 1bbb221 |
