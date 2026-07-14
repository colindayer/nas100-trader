---
type: changelog
tags: [changelog, meta]
---
# AI Change Log

_Mirrored from `docs/AI_CHANGELOG.md` by obsidian_bridge.py._

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
| 2026-07-10 | Lead Engineer / Claude Code | **Obsidian Bridge built** (scripts/obsidian/build_obsidian.py + README): 16 generated notes under vault/auto/ (daily, AI session log, git commits, bugs fixed, monitoring, trade journal, research, dashboard snapshot + 7 indexes), AUTO-marker managed sections | verified: idempotent, human edits outside markers survive, 33 hand-written notes byte-untouched, 0 broken wikilinks; py_compile OK | 1bbb221 |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge: post-commit auto-sync (1bbb221 trail) | git post-commit hook | b146b9b |
| 2026-07-10 | Obsidian Bridge / automated | Bridge follow-up: enrich changelog row with verification evidence; register b... | git post-commit hook | 80c63d5 |
| 2026-07-10 | Obsidian Bridge / automated | Commit post-commit-hook residue (changelog/state/vault rows for 80c63d5) [hoo... | git post-commit hook | e4ba048 |
| 2026-07-10 | Obsidian Bridge / automated | Hook installer: skip [bridge-auto] commits (loop guard, from parallel session) | git post-commit hook | b82759a |
| 2026-07-10 | Obsidian Bridge / automated | Fix: prevent infinite post-commit loop (skip [bridge-auto] commits) | git post-commit hook | aaa876b |
| 2026-07-10 | Obsidian Bridge / automated | Add scripts/README.md placeholder | git post-commit hook | 25b02a0 |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | c9c26b4 |
| 2026-07-10 | Obsidian Bridge / automated | Remove test placeholder | git post-commit hook | 70a88b2 |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 259f3dd |
| 2026-07-10 | Obsidian Bridge / automated | Research OS v1: ideas/papers/experiments intake + new_idea/new_paper generators | git post-commit hook | 30a78e4 |
| 2026-07-10 | Lead Engineer / Claude Code | **Research OS v1**: research/{ideas,papers,experiments}+README, scripts/research/new_idea.py + new_paper.py (templated, backlinked, no-overwrite) | py_compile, create/refuse/slug tests all pass; seeded DIX idea + Zarattini paper | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 5d68a5a |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog + state for Research OS v1 [bridge-auto] | git post-commit hook | cc0138d |
| 2026-07-10 | Obsidian Bridge / automated | Experiment Pipeline: queue/experiments/archive lifecycle + new_experiment/pro... | git post-commit hook | ee19aee |
| 2026-07-10 | Lead Engineer / Claude Code | **Experiment Pipeline**: research/{queue,archive} + new_experiment.py/promote_experiment.py (unique IDs, lifecycle gates, reviewer!=author enforcement) | end-to-end lifecycle test incl. 3 refusal gates; false test-state reset to truthful queued | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | fd09e4f |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog + state for Experiment Pipeline [bridge-auto] | git post-commit hook | 147896b |
| 2026-07-10 | Obsidian Bridge / automated | Daily Ops Report 2026-07-10: no production bug detected, system nominal | git post-commit hook | 970d46b |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | eac5f8a |
| 2026-07-10 | Obsidian Bridge / automated | Nightly Ops Runner v1: scripts/ops/daily_check.py -> docs/DAILY_OPS_REPORT.md | git post-commit hook | b070fa7 |
| 2026-07-10 | Ops Runner (built by Lead Engineer / Claude Code) | **Nightly Ops Runner v1**: scripts/ops/daily_check.py generates docs/DAILY_OPS_REPORT.md (verdict HEALTHY/ACTION REQUIRED, exit 0/2) | compile + healthy run + negative injection test all pass | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 201c6df |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog + state for Nightly Ops Runner v1 [bridge-auto] | git post-commit hook | a78595d |
| 2026-07-10 | Obsidian Bridge / automated | ROADMAP_V2: 10 proposed systems for the research platform (design only, windo... | git post-commit hook | 1eebf04 |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 24759f0 |
| 2026-07-10 | Obsidian Bridge / automated | Commit run_experiment.py from parallel session (compiles, research-only, no p... | git post-commit hook | a5e2ef0 |
| 2026-07-10 | Obsidian Bridge / automated | Add automatic paper ingestion: scripts/research/import_paper.py | git post-commit hook | 9c189d7 |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 825f111 |
| 2026-07-10 | Obsidian Bridge / automated | AI Task Router: orchestration layer (scan/sort/dispatch/state), infrastructur... | git post-commit hook | 39482e5 |
| 2026-07-10 | Lead Engineer / Claude Code | **AI Task Router** (scripts/router/): file-based task queue in research/queue/ (TASK-*), priority dispatch to Claude/GLM/Qwen/Fable/OpenClaw, dependency holds, state ledger | 3-task routing test, idempotency, persistence, human-note preservation, EXP-note isolation all verified | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | aa7a711 |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog + state for AI Task Router [bridge-auto] | git post-commit hook | 26772ba |
| 2026-07-10 | Obsidian Bridge / automated | TensorTrade evaluation: installs w/ surgery (py3.13), smoke test PASS, verdic... | git post-commit hook | e5d9102 |
| 2026-07-10 | Research eval / Claude Code | **TensorTrade evaluation** -> DEFER: viable in isolated venv (smoke test PASS on py3.13 w/ dep surgery) but philosophy collision (industrialized overfit), prop mismatch (no native brackets), standing dep tax | docs/TENSORTRADE_EVALUATION.md; scratchpad venv, repo env untouched | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | b1f800d |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog for TensorTrade evaluation [bridge-auto] | git post-commit hook | 69cb675 |
| 2026-07-10 | Obsidian Bridge / automated | Router: automatic task execution (executor.py) + follow-up chains | git post-commit hook | 985c4af |
| 2026-07-10 | Lead Engineer / Claude Code | **Router auto-execution**: executor.py runs whitelisted mapped scripts on dispatch, captures rc/stdout/stderr/time, auto-status, queues deduped follow-up chains | verified: paper->index->obsidian chain drained over 3 runs, 4th run no-op, failure->review, real artifacts | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 7436dfb |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog + state for router auto-execution [bridge-auto] | git post-commit hook | 8137c4a |
| 2026-07-10 | Obsidian Bridge / automated | Losing-trade forensics: L1 Alpaca OVN -1,567 (state-loss oversize + missed ex... | git post-commit hook | 6a97f08 |
| 2026-07-10 | Investigator / Claude Code | **Losing-trade forensics** (docs/LOSING_TRADE_FORENSICS.md): 2 losers total; L1 -1,567 = state-loss oversize (134 vs 33) + missed exit + naked (all since fixed); L2 = S5 mid-bar entry, within stop envelope; recommends fill ledger as single fix; flags unattributable ticket 335622424 | sizing reconstruction + MT5 snapshots + equity trail; corrects 'pre-existing' claim | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | a8e2623 |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog for losing-trade forensics [bridge-auto] | git post-commit hook | 6039c5b |
| 2026-07-10 | Obsidian Bridge / automated | Fill ledger: record every order at the place_order_safe boundary (logging only) | git post-commit hook | 14c10e6 |
| 2026-07-10 | Lead Engineer / Claude Code | **Fill ledger** (fill_ledger.py -> logs/fills.csv): signal vs bid/ask/fill per order, derived spread+slippage bps, dry-run labeled, fail-safe by construction | 17/17 tests; dry-runs clean; constants byte-identical; 0 sizing/filter lines changed | (see git) |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 9fc5770 |
| 2026-07-10 | Obsidian Bridge / automated | Bookkeeping: changelog + state for fill ledger [bridge-auto] | git post-commit hook | b71c8cb |
| 2026-07-10 | Obsidian Bridge / automated | tools/analyze_execution.py: execution-quality analytics over logs/fills.csv (... | git post-commit hook | af5a494 |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 77d6191 |
| 2026-07-10 | Obsidian Bridge / automated | Setup-supply analysis: setups at 3y highs (96th pct), filters not over-reject... | git post-commit hook | 18322de |
| 2026-07-10 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | b8fc385 |
| 2026-07-11 | Obsidian Bridge / automated | tools/audit_signal_parity.py: day-by-day expected vs live signal counts (S1/S... | git post-commit hook | 1557811 |
| 2026-07-11 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | c346b7a |
| 2026-07-11 | Obsidian Bridge / automated | Macro regime survey: 6 filter families reviewed, 1 survivor (VIX term-structu... | git post-commit hook | 2d97b34 |
| 2026-07-11 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 87e98ae |
| 2026-07-11 | Obsidian Bridge / automated | EXP-20260711-01 run: VIX term-structure gate — S1 no value; S5 beats level ga... | git post-commit hook | 2f623e8 |
| 2026-07-11 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 703cbd0 |
| 2026-07-11 | Obsidian Bridge / automated | EXP-20260711-01 adversarial review: VALIDATED_FOR_FORWARD_SHADOW — look-ahead... | git post-commit hook | d1ba90c |
| 2026-07-11 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | d9df262 |
| 2026-07-11 | Obsidian Bridge / automated | Head of Research program: universe expansion (11 keepers, pooled 2.32, corr 0... | git post-commit hook | 1a7174c |
| 2026-07-11 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 9de8b8a |
| 2026-07-12 | Obsidian Bridge / automated | Evidence cycle: ETF review VALIDATED_FOR_FORWARD_SHADOW (9 survivors, corr 0.... | git post-commit hook | e99c0dd |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | b6f294c |
| 2026-07-12 | Obsidian Bridge / automated | ATR compression filter: REJECT (adversarial review) — look-ahead + post-hoc s... | git post-commit hook | 9541f4e |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 0688da5 |
| 2026-07-12 | Obsidian Bridge / automated | Survey triage: #1 citation verified REAL but mechanism stated backwards (intr... | git post-commit hook | 0a74e18 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | a3796c1 |
| 2026-07-12 | Obsidian Bridge / automated | Evidence month: EVIDENCE_LEDGER (daily/weekly) + MONTH_1_LIVE_REPORT comparat... | git post-commit hook | 29c30cc |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 84f7a01 |
| 2026-07-12 | Obsidian Bridge / automated | State: standing directive -- evidence month [bridge-auto] | git post-commit hook | ce8e406 |
| 2026-07-12 | Obsidian Bridge / automated | Router state + execution-analysis placeholder (residue) [bridge-auto] | git post-commit hook | c408307 |
| 2026-07-12 | Obsidian Bridge / automated | Monthly evidence committee report (--committee mode): research vs shadow vs l... | git post-commit hook | 489a709 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | ae5d61c |
| 2026-07-12 | Obsidian Bridge / automated | ETF forward-shadow review day 1: all NEEDS MORE DATA; decision rule pre-regis... | git post-commit hook | 9290fa6 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 13f8c05 |
| 2026-07-12 | Obsidian Bridge / automated | Drift investigation: sizing verified clean (display-rounding false alarm), re... | git post-commit hook | ddb02a0 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 2b67146 |
| 2026-07-12 | Obsidian Bridge / automated | Macro filter review: ts corroborated (6/6), DXY parked (6/6 but era-lumpy, -5... | git post-commit hook | e0ea784 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 55ea5d2 |
| 2026-07-12 | Obsidian Bridge / automated | Overnight momentum review: REJECT — RFS mechanism replicates at ETF level but... | git post-commit hook | e3f5d8f |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 33e5cec |
| 2026-07-12 | Obsidian Bridge / automated | Graveyard audit: 33 rejections reviewed — 30 STAND, 2 refined/partially super... | git post-commit hook | 674315e |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 155d5b8 |
| 2026-07-12 | Obsidian Bridge / automated | Prop readiness: design ready, evidence not — 8 blockers ranked; decision belo... | git post-commit hook | b86a445 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | cb3c5d2 |
| 2026-07-12 | Obsidian Bridge / automated | S5 re-entry divergence quantified: KEEP — 12 extra trades/7.5y, breakeven, de... | git post-commit hook | e839f8b |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 23a1351 |
| 2026-07-12 | Obsidian Bridge / automated | Research freeze: backlog triaged — 3 SHADOW, 5 WAITING, 5 REJECTED (incl. moo... | git post-commit hook | 699bbc6 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 3443134 |
| 2026-07-12 | Obsidian Bridge / automated | Command Center: one-page operational dashboard (7 sections, summarizes existi... | git post-commit hook | a655536 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 428c8da |
| 2026-07-12 | Obsidian Bridge / automated | Streamlit dashboard v2: 7 pages (HOME/LIVE/SHADOW/RESEARCH/EVIDENCE/LOGS/SETT... | git post-commit hook | 115f30d |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 5e7fb88 |
| 2026-07-12 | Obsidian Bridge / automated | FINDING: S2 gold FVG structurally inert live — daily-gap concept on hourly ba... | git post-commit hook | 70b8487 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 26ab180 |
| 2026-07-12 | Obsidian Bridge / automated | FIX S2: port to validated daily-FVG lineage (human-authorized) | git post-commit hook | 614e1ba |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 0ea4154 |
| 2026-07-12 | Obsidian Bridge / automated | Strategy Validation Audit: 8 questions x 8 strategies — S3 provenance drift f... | git post-commit hook | a219f81 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | ac0491d |
| 2026-07-12 | Obsidian Bridge / automated | Cockpit upgrade: 9-page decision dashboard — status cards, AI Commander (rule... | git post-commit hook | f34575b |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 60d7f06 |
| 2026-07-12 | Obsidian Bridge / automated | LLM bridge (GLM/Qwen subagents) + vault update | git post-commit hook | 56e9d11 |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | e8843fe |
| 2026-07-12 | Obsidian Bridge / automated | S3 validation review: research vs live implementation | git post-commit hook | c70477d |
| 2026-07-12 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 205ad79 |
| 2026-07-13 | Obsidian Bridge / automated | Bookkeeping: clock RESET to 2026-07-14 after signal-touching S2 fix (614e1ba) | git post-commit hook | d454e02 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | cb605dd |
| 2026-07-13 | Obsidian Bridge / automated | Decision log: S3 drift KEEP AS-IS (human 2026-07-13) — safe subset, defer to ... | git post-commit hook | 0e13cbd |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 9ff3654 |
| 2026-07-13 | Obsidian Bridge / automated | Fix nas100-update task (0x800710E0/4320): run as SYSTEM + non-hanging git pull | git post-commit hook | bcbedfc |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | d4eba05 |
| 2026-07-13 | Obsidian Bridge / automated | Validation Audit #2 (weekend exposure): S5 benefits from weekend holds, S3 ha... | git post-commit hook | 96d8ed3 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 65b05c9 |
| 2026-07-13 | Obsidian Bridge / automated | Knowledge graph: KNOWLEDGE_GRAPH.md (8 strategies x 11 facets) + knowledge_gr... | git post-commit hook | 634eb49 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 5b98cfa |
| 2026-07-13 | Obsidian Bridge / automated | Dashboard cockpit v3 + vault backlinks + repo/data audits (docs+view only) | git post-commit hook | b519749 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 2d2af0a |
| 2026-07-13 | Obsidian Bridge / automated | Project Constitution: single authoritative survival document (10 sections — p... | git post-commit hook | ec52a14 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 244b855 |
| 2026-07-13 | Obsidian Bridge / automated | Trade Explorer page: investigate any trade in <30s (read-only view layer) | git post-commit hook | 6d96c65 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 6ff1252 |
| 2026-07-13 | Obsidian Bridge / automated | Trading OS.app: native macOS launcher shell (presentation+launcher only) | git post-commit hook | d07c49f |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | d9e4c58 |
| 2026-07-13 | Obsidian Bridge / automated | Alpha Leak Audit: forensic implementation-drift pass over all 8 strategies — ... | git post-commit hook | be98a67 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 912a570 |
| 2026-07-13 | Obsidian Bridge / automated | Forensic Investigation: Phase 1 production forensics + Phase 2 regime audit +... | git post-commit hook | 534d2f6 |
| 2026-07-13 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 996aee8 |
| 2026-07-14 | Obsidian Bridge / automated | Fix overnight CRASH (NoneType format): broker.py place_order_safe logged TP={... | git post-commit hook | a6c2c8a |
| 2026-07-14 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 0d59b39 |
| 2026-07-14 | Obsidian Bridge / automated | Forensic Pipeline Audit (5 phases): end-to-end trace, signal audit (every mis... | git post-commit hook | 26bebf0 |
| 2026-07-14 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 21b7283 |
| 2026-07-14 | Obsidian Bridge / automated | Multi-model bridge: one-command delegate + bridge-status (reuses llm_bridge/r... | git post-commit hook | 87ce725 |
| 2026-07-14 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 670154c |
| 2026-07-14 | Obsidian Bridge / automated | Infra: fix dashboard :8501 reliability + finish bridge status + AI-infra doc | git post-commit hook | 08fb5b5 |
| 2026-07-14 | Obsidian Bridge / automated | Obsidian bridge auto-sync [bridge-auto] | git post-commit hook | 51a2c87 |
| 2026-07-14 | Obsidian Bridge / automated | Operational readiness audit: 15 ranked ops-failure risks (P*I) + tiered remed... | git post-commit hook | c075c01 |
