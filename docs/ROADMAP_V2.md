# ROADMAP V2 — Quant Research Platform evolution

_Design only; nothing here is implemented. Assumes production is FROZEN for the
30-day monitoring window — every item below is research/ops-side and none touches
`live_trader.py`, strategies, brokers, or risk logic. Fits the existing
architecture (AI_OPERATING_SYSTEM.md roles + Research OS + Experiment Pipeline +
Ops Runner + Obsidian bridges + Streamlit dashboard); duplicates nothing._

## What already exists (do not rebuild)

| Capability | Owner artifact |
|---|---|
| Idea/paper intake + templates | `scripts/research/new_idea.py`, `new_paper.py` |
| Experiment lifecycle w/ gates | `new_experiment.py`, `promote_experiment.py`, `run_experiment.py` |
| Nightly health verdict | `scripts/ops/daily_check.py` → `DAILY_OPS_REPORT.md` |
| Vault knowledge notes | `scripts/obsidian/build_obsidian.py` (vault/auto/) |
| Commit-driven changelog/state sync | `scripts/obsidian_bridge.py` + post-commit hook |
| Streamlit dashboard skeleton | `dashboard/app.py` |
| Validation engine | `edge_hunt.py` (gauntlet + 6/6 sweep), `prop_sim.py` |
| Process law | AI_OPERATING_SYSTEM.md, CURRENT_PROJECT_STATE.md, AI_CHANGELOG.md |

---

## Proposed systems (in recommended implementation order)

### 1. Bridge Unification (tech debt, do first)
Two Obsidian generators coexist (`scripts/obsidian_bridge.py` commit-hook sync vs
`scripts/obsidian/build_obsidian.py` knowledge notes) — an acknowledged violation
of the no-duplication law, born from parallel sessions.
- **Why:** two writers to one vault will eventually fight (same daily-journal note,
  divergent changelog mirrors). Every later item builds on vault output.
- **Dependencies:** none.
- **Complexity:** **S** (merge into one package `scripts/obsidian/`, hook calls it
  with `--post-commit`; keep both feature sets).
- **Impact:** medium — removes the platform's only structural inconsistency.
- **Risks:** low; worst case a malformed vault note (regenerable).

### 2. Experiment Runner + Automatic Validation Harness
Extend the existing `run_experiment.py` so every experiment runs against a
**standard result schema**: script prints/writes `result.json` (IS/OOS Sharpe, DD,
trades, corr, splits-passed); the harness stamps the note's backtest table and
drafts the gauntlet-checklist ticks automatically.
- **Why:** today the gauntlet is manual transcription — the exact place where
  humans/AIs fudge or mistype. Machine-filled results = trustworthy graveyard.
  This is "automatic validation" without giving AIs authority: the harness FILLS,
  the Reviewer + human still JUDGE.
- **Dependencies:** #1 optional; `edge_hunt.gauntlet()` already importable.
- **Complexity:** **M**.
- **Impact:** high — the core of research throughput and honesty.
- **Risks:** schema too rigid for exotic experiments → allow a free-form appendix;
  never auto-promote on green numbers (promotion stays human-gated).

### 3. Memory Architecture v2 — machine-readable state + graveyard index
Add `state/` JSON artifacts generated from the markdown sources: `graveyard.json`
(every rejected idea/experiment with reason), `experiments.json` (pipeline state),
`book.json` (validated strategies + params). `new_idea.py` gains a duplicate check
against `graveyard.json` (warn: "similar to rejected X").
- **Why:** markdown memory works for humans; agents grep it lossily. The single
  most repeated failure mode across sessions is re-testing dead ideas — a
  machine-checkable graveyard closes it. Also gives the dashboard clean inputs.
- **Dependencies:** none (generators read existing md).
- **Complexity:** **M**.
- **Impact:** high — directly attacks the top recurring waste.
- **Risks:** JSON drifting from markdown → generate JSON FROM markdown only
  (one-way, md stays source of truth).

### 4. Multi-Model Review Protocol (Claude / GLM / Qwen / ChatGPT)
`promote_experiment.py --to gauntlet` additionally emits
`research/reviews/EXP-...-request.md`: a self-contained adversarial-review brief
(claim, data, script path, "try to refute" instructions) that the human pastes
into a DIFFERENT model; the reviewer's verdict file is required by
`--to validated` (instead of just a `--reviewer` name string).
- **Why:** author≠reviewer is currently enforced by a string comparison — a
  courtesy, not a control. A required verdict artifact makes the review real and
  archives WHY something passed. This is the cheapest form of multi-model
  collaboration that actually adds safety (precedent: cross-model review caught
  the fd0ff25 startup bugs).
- **Dependencies:** #2 (reviews reference the standard result.json).
- **Complexity:** **S/M**.
- **Impact:** high per unit effort.
- **Risks:** friction → keep the brief short; single-reviewer requirement, not a panel.

### 5. Monitoring v2 — VPS-side runner + Telegram digest + month-end builder
(a) schedule `daily_check.py` on the VPS (where the real logs live) with its
exit-code wired to a Telegram nightly digest (send only on ACTION REQUIRED, plus
a weekly summary); (b) `scripts/ops/month_report.py` that assembles
`MONTH_1_LIVE_REPORT.md` from the accumulated daily reports + trade ledger — the
go/no-go artifact the whole window exists to produce.
- **Why:** the Mac-side runner sees only Mac logs; the decision data is on the VPS.
  The month-end report is currently an unbuilt promise with a deadline (~day 30).
- **Dependencies:** none (daily_check exists; schtasks pattern established).
- **Complexity:** **M** (mostly ledger-parsing for realized R/slippage).
- **Impact:** high — this produces the funding decision.
- **Risks:** Windows quirks (known playbook: PYTHONUTF8, ASCII, schtasks).

### 6. Dashboard Integration (read-only research/ops cockpit)
Point the existing `dashboard/app.py` at files that now exist: DAILY_OPS_REPORT
verdict, experiment pipeline state (`experiments.json` from #3), graveyard count,
changelog tail, equity/risk-scale series parsed from logs.
- **Why:** one glance replaces five file-opens; makes the daily checklist ~1 min.
- **Dependencies:** #3 (clean JSON inputs); #5 for VPS data files (synced or displayed as "VPS-side").
- **Complexity:** **S/M** (skeleton exists).
- **Impact:** medium — quality-of-life, not correctness.
- **Risks:** dashboard drift if it parses markdown directly → consume only `state/` JSON.

### 7. Paper Ingestion v1 (local-first, no internet)
`research/papers/inbox/` for dropped PDFs; `scripts/research/ingest_paper.py`
extracts text (pypdf, already used in-session), pre-fills the `new_paper.py`
template (title/abstract guess), moves the PDF to `research/papers/pdf/`.
- **Why:** papers arrive as PDFs (Zarattini did); manual transcription loses the
  honest-assessment step half the time. Local-only keeps the no-internet rule.
- **Dependencies:** none.
- **Complexity:** **S/M**.
- **Impact:** medium.
- **Risks:** PDF extraction is messy → extraction fills a draft, human finishes it.

### 8. Agent Orchestration v1 — file-based task queue
`ops/queue/` with one markdown task per file (`role:`, `status:`, `context:`
frontmatter). Any AI session's start-protocol adds: "claim the oldest open task
for your role." OpenClaw (or the human) enqueues; sessions dequeue. No daemon, no
framework — git IS the coordination bus, matching the existing hook-driven design.
- **Why:** today tasks travel via human copy-paste between models; a queue makes
  handoffs durable and auditable, and lets nightly jobs enqueue follow-ups
  ("ACTION REQUIRED → auto-create triage task").
- **Dependencies:** #5 (ops runner enqueues on red verdict) for full value.
- **Complexity:** **M**.
- **Impact:** medium-high — the difference between "AIs cooperate when the human
  ferries context" and "the repo itself assigns work".
- **Risks:** queue rot → daily_check flags tasks older than N days.

### 9. Strategy Promotion Pipeline (post-window only)
The formal path from `archive/ (validated)` to the live book:
`scripts/research/propose_promotion.py EXP-...` generates a **promotion dossier**
— parity checklist (same stop/RR live vs test), risk-layer plan (which RISK_*
constant, which session), correlation-to-book table, required sign-offs (Reviewer
+ human), and an explicit "resets the clock" acknowledgment. Integration itself
remains a hand-written Lead Engineer PR.
- **Why:** the pipeline currently ends at "cleared for human decision" with no
  defined next step; ad-hoc integration is how parity bugs were born.
- **Dependencies:** #2 (result schema), #4 (review artifact).
- **Complexity:** **M/L**.
- **Impact:** high — but only after the window; deliberately LAST.
- **Risks:** highest of the list (touches the live boundary) → dossier generates
  documents only; code integration stays manual and reviewed.

### 10. Knowledge Graph Enrichment
Bidirectional auto-backlinks (idea ↔ experiment ↔ paper ↔ strategy note) written
into the AUTO blocks by the unified bridge, plus a Dataview "research pipeline"
board in vault/auto/ (queued/running/gauntlet/archived counts, stale-experiment
flags).
- **Why:** the graph currently links downward (experiment → idea) but not back;
  orphan detection and pipeline visibility come free once #1/#3 exist.
- **Dependencies:** #1, #3.
- **Complexity:** **S**.
- **Impact:** low-medium (navigability, stale-work detection).
- **Risks:** minimal.

---

## Explicitly NOT recommended (scope discipline)

- **Internet-scraping paper/idea ingestion** — violates the no-internet rule of
  research sessions; ingestion stays local-drop.
- **Auto-promotion of validated experiments** — promotion is human-gated forever;
  green numbers have lied before (EWA/EWC split-luck).
- **Agent frameworks/daemons (LangChain-style orchestration)** — the git+files
  bus already works and is auditable; a resident daemon adds failure modes.
- **Any new venue/broker/strategy work during the window** — clock-reset rule.
- **Dashboard write-actions** (kill switches, order buttons) — the dashboard is
  read-only by design; control stays in the CLI + scheduler.

## Sequencing summary

| Phase | Items | Rationale |
|---|---|---|
| Now (window-safe) | 1, 2, 3 | debt + the research core (harness, memory) |
| Next | 4, 5 | review rigor + the month-end deliverable machinery |
| Then | 6, 7, 8 | cockpit, ingestion, orchestration (quality of life) |
| Post-window only | 9, then 10 polish | the live boundary, once the month verdict exists |

Total: 2×S, 5×M, 1×S/M... realistically ~2–3 weeks of session-work, all of it
frozen-window-compatible except #9.
