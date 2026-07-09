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
