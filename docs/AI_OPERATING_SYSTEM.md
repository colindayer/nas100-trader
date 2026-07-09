# AI OPERATING SYSTEM — how every AI cooperates on this project

_The contract for all AI sessions (Claude Code, Fable, ChatGPT, Qwen, GLM/z.ai,
OpenClaw-orchestrated agents) and the human operator. Goal: every session builds on
previous work instead of rediscovering the repository. **The repo IS the memory —
no chat thread is.**_

---

## 1. The three laws (every AI, every session)

1. **`docs/CURRENT_PROJECT_STATE.md` is the source of truth.** Read it first.
   Never re-audit, never rediscover, never rewrite architecture. If it's wrong,
   fix IT, don't fork reality.
2. **Evidence before edits.** Code changes require a confirmed issue (crash,
   exception, broker failure, wrong/naked order, parity mismatch, alert, failed
   deploy). "Might be better" is not a trigger. During the 30-day statistics
   window, any signal-touching change resets the clock.
3. **Every change leaves a trail:** commit to `main` + entry in
   `docs/AI_CHANGELOG.md` + (if state changed) update `CURRENT_PROJECT_STATE.md`.
   An undocumented change does not exist — the next session will undo it.

**Frozen surfaces (no AI touches without explicit human sign-off):** strategy
entry logic/filters/constants; mandatory broker-side SL/TP; kill-switches &
DD-throttle; ASCII output; `get_bars` bar-count contract; secrets out of git;
the BTC reconcile guard. (Full list in CURRENT_PROJECT_STATE.)

---

## 2. Roles & responsibilities (by strength, not by brand)

| Role | Default assignee | Responsibilities | May write code? |
|---|---|---|---|
| **Lead Engineer** | Claude Code (interactive) | production reliability, parity, confirmed-bug fixes, releases to `main`, state-doc upkeep | ✅ (evidence-gated) |
| **Research Analyst** | Fable / long-context model | edge hunts, SSRN/paper reviews, prop-math Monte-Carlo, large log forensics | ✅ research scripts only — **never `live_trader.py`/brokers** |
| **Reviewer/Skeptic** | a DIFFERENT model than the author | verify claims in changed code/docs, adversarial re-check (the fd0ff25 startup bug was caught exactly this way) | ❌ (report only) |
| **Ops Runner** | Qwen / GLM / cheap local model, or OpenClaw cron | nightly/daily mechanical jobs: run checklists, tail logs, produce summaries | ❌ (runs commands, writes reports) |
| **Brainstorm/Drafting** | ChatGPT / any chat model | idea generation, prompt drafting, explainers | ❌ (output goes to `12-Ideas`, then the gauntlet) |
| **Orchestrator** | OpenClaw | schedules the jobs below, routes tasks to roles, never edits code itself | ❌ |
| **Human (Colin)** | — | approvals on frozen surfaces, funding decisions, VPS/dashboard eyes, secrets | final say |

**Rules of engagement between roles:**
- Research NEVER merges to the live path; it ships scripts + a FINDINGS entry, and
  the Lead Engineer integrates (this firewall exists because a research session once
  left `live_trader.py` unparseable).
- Author ≠ Reviewer for anything touching money paths.
- Two AIs never work the same file concurrently; if unavoidable, branch + the Lead
  Engineer merges (past collisions: stash/rebase dances on `main`).

## 3. Handoffs (session → session)

**Session start (any AI, any role):**
1. Read `CURRENT_PROJECT_STATE.md` → 2. `git log --oneline -10` since the state
   doc's last commit → 3. read today's logs / alerts relevant to your role →
4. read your predecessor's last `AI_CHANGELOG.md` entry. Then work.

**Session end (mandatory):**
- Commit work (or explicitly `git stash drop`/restore — never leave a dirty tree;
  a dangling uncommitted fix nearly shipped broken once).
- Append to `docs/AI_CHANGELOG.md`:
  `| date | role/model | what changed | evidence/verification | commits |`
- If blockers/status moved: update `CURRENT_PROJECT_STATE.md` in the same commit.
- If mid-task: write the exact resume point into the changelog entry ("resume at:
  X failing, tried Y, next try Z") — the next session starts there, not from zero.

**Cross-AI handoff prompt template** (when the human moves a task between tools):
paste the target's role, `CURRENT_PROJECT_STATE.md`, and the last changelog entry.
Nothing else is required — if more context is needed, the docs are incomplete: fix them.

## 4. Memory hierarchy

| Layer | Location | Contents |
|---|---|---|
| Source of truth | `docs/CURRENT_PROJECT_STATE.md` | architecture, status, blockers, frozen list |
| Change memory | `docs/AI_CHANGELOG.md` + git history | who did what, when, evidence |
| Domain memory | `FINDINGS.md`, `HUNT_LOG.md`, `SWEEP_SUMMARY.md` | every edge tested, every rejection (never re-test the graveyard) |
| Operating knowledge | `vault/` (Obsidian) | philosophy, strategies, incidents, journal, roadmap |
| Governance docs | `docs/*` (parity, readiness, monitoring, playbook) | the standing decisions |
| Ephemeral | chat threads, model memory | **untrusted** — anything worth keeping gets written to the repo |

Rule: chat memory is a cache, the repo is the database. A fact that matters and
lives only in a conversation is a bug in this operating system.

## 5. Nightly jobs (Ops Runner / OpenClaw cron)

| Time (UTC) | Job | Command | Output |
|---|---|---|---|
| 21:30 | Health snapshot | `python status.py` on VPS | append to `logs/ops_daily.md`; Telegram if any task LastResult != 0 |
| 21:35 | Signal/skip tally | grep SIGNAL + skip-reasons from `logs/mt5_*.log` | daily journal line (vault 11-Daily-Journal) |
| 21:40 | Error sweep | grep CRASH/FAIL/NAKED/Traceback in logs | alert if non-empty, else silence |
| 22:00 | S3 age check | list open MT5 positions tagged S3 + age | alert at ≥4 trading days |
| Sun 20:00 | Weekly research (optional) | `python edge_hunt.py --sweep` | `SWEEP_SUMMARY.md`; PASS rows flagged to Research Analyst — **6/6 or reject** |
| Fri 21:00 | Weekly review pack | ledger + slippage + counts per NEXT_30_DAY_MONITORING_PLAN §3 | weekly note in vault |

Nightly jobs REPORT; they never modify code. A red nightly report is what
authorizes the Lead Engineer's next fix session.

## 6. Research pipeline (idea → live)

```
Idea (any AI/human) → vault/12-Ideas
  → Research Analyst codes a standalone script (research/, never live path)
  → THE GAUNTLET (edge_hunt): IS/OOS, costs, corr<0.3, regime, 6/6 split robustness
  → reject (default): one line in FINDINGS/HUNT_LOG — the graveyard is memory
  → pass: Reviewer (different model) tries to kill it; survives → human decision
  → Lead Engineer integrates behind the existing risk layers; parity-tested
  → NEVER during the 30-day window (clock reset rule)
```
History: ~30 ideas in, ~2 survived long-term. The pipeline's job is to say no.

## 7. Monitoring pipeline (the current phase)

- **Continuous:** Telegram (FILL / CRASH / watchdog / kill-switch) → human phone.
- **Daily (5 min, human or Ops Runner):** checklist in NEXT_30_DAY_MONITORING_PLAN §2.
- **Weekly (Fri):** review checklist §3; count parity-blocker occurrences
  (same-day re-entry, S3 age); Reviewer sanity-checks the week's numbers.
- **Day 30:** Lead Engineer + Research produce `MONTH_1_LIVE_REPORT.md`;
  human takes the go/no-go funding decision per PROP_CHALLENGE_PLAYBOOK.
- **Escalation:** any confirmed-issue trigger (see law #2) → Lead Engineer session
  with the full fix protocol (root cause → fix → py_compile → dry-run → verify →
  commit → state doc → changelog → stop).

## 8. Deployment pipeline

```
change (evidence-gated) → py_compile + dry-run on Mac → commit to main → push
  → GitHub Actions picks up next cron (Alpaca paper)
  → VPS auto-pulls main within 30 min (nas100-update task) → next Nas100Bot-* run
  → verification: status.py on VPS / Actions tab green / Telegram quiet
```
- Only `main` deploys. No AI pushes a broken `main`: compile+dry-run are mandatory
  pre-push. Workflow YAML changes go through the human (token lacks `workflow` scope).
- Rollback: `git revert` the commit; VPS picks up the revert on next pull.
- Secrets never travel through this pipeline (config.ini local; GitHub Secrets).

## 9. Anti-patterns (all previously observed — hence banned)

- Re-auditing the repo "to get oriented" (burns a session; read the state doc).
- Leaving uncommitted changes in the tree at session end.
- A research AI editing `live_trader.py` (shipped a SyntaxError once).
- Re-testing graveyard ideas (EWA/EWC, London breakout, SSRN momentum, forex sweep…).
- Trusting a single-split backtest PASS (split-luck; 6/6 or nothing).
- Creating a new doc when an existing one covers the topic (update, don't duplicate).
- Pasting secrets into chats (rotation now owed before real money).
- "Improving" during the monitoring window.

---
_This document governs process. Trading behavior is governed by the frozen
surfaces + monitoring plan. Change this file the same way as any other: commit +
changelog entry._
