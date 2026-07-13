# PROJECT CONSTITUTION — NAS100 Trading OS

_The authoritative document. If every current AI session and the original operator
disappeared tomorrow, a new engineer should be able to read this one file and safely
continue. Written 2026-07-13. Documentation only — changes nothing. When this and any
other doc disagree, the linked source-of-truth doc wins; this is the map, not the
territory._

---

## 1. PROJECT PURPOSE

**What it is.** An automated, multi-strategy, cross-asset trading system (NAS100
index via CFD/ETF, gold, US equities, BTC) whose near-term goal is to **pass a
prop-firm challenge** (FundedNext Stellar / FTMO, via Pepperstone MT5 + Alpaca paper
+ Binance/CFD BTC) to earn funded-account income. It runs a book of ~8 validated
strategies with broker-side risk controls, a research pipeline that feeds it, and a
governance layer that decides what is allowed to trade real money.

**What it is NOT.**
- Not a high-frequency or latency-sensitive system (hourly/daily bars).
- Not a discretionary tool — no human picks trades; strategies are rules.
- Not an ML/black-box system — no LLM makes trading decisions (LLMs only document,
  review, and orchestrate). TensorTrade was evaluated and DEFERRED.
- Not yet trading real money — **zero real-money fills have ever occurred.** It is a
  validated design awaiting one clean month of live evidence.

**Objective.** Pass a challenge with the balanced sizing (vol_target ~0.16 → ~50%
pass/attempt in 3 months, ~68–82% across 2–3 parallel accounts in ~4 months, <~$1k
fees at risk). Then trade the funded account for supplementary income.

**Funding path.** Evidence month (now) → month-end committee (2026-08-16) → if the
report is green, buy 2–3 parallel FundedNext challenges at the config sizing → pass →
funded. If red, stop for free. See [CHALLENGE_VS_FUNDED_VS_LIVE.md](CHALLENGE_VS_FUNDED_VS_LIVE.md),
[PROP_CHALLENGE_PLAYBOOK.md](PROP_CHALLENGE_PLAYBOOK.md), [PROP_READINESS.md](PROP_READINESS.md).

**Evidence philosophy.** The edge is UNCONFIRMED live — it exists in backtest and a
handful of bug-corrupted early trades, nothing clean. Therefore: **evidence over
intuition.** Nothing is promoted on a backtest alone; a strategy must survive the
gauntlet, then forward-shadow, then a live month, then a committee. The monthly
evidence report is the single source of truth. Weak evidence is rejected, not
argued around.

---

## 2. SYSTEM ARCHITECTURE

```
   RESEARCH        idea/paper intake → experiment (edge_hunt / gauntlet)
      │            research/ ideas, papers, experiments; scripts/research/
      ▼
   VALIDATION      the gauntlet: IS/OOS walk-forward, costs on (3bps/side),
      │            OOS Sharpe>0.5, |corr QQQ|<0.3, regime check, 6/6 split
      │            robustness. AUTHOR ≠ REVIEWER (adversarial review).
      ▼
   SHADOW          forward-log would-be signals with NO orders, until a
      │            pre-registered day/rate threshold. shadow_signals.csv.
      ▼
   COMMITTEE       month-end: research expectation vs shadow vs live fills.
      │            FAILS_FORWARD_EVIDENCE → rejected; PASSES → human review.
      ▼
   PRODUCTION      live_trader.py dispatches validated strategies to brokers
      │            with broker-side SL/TP, DD-throttle, kill-switches.
      ▼
   EVIDENCE        fills.csv + daily ledger + ops report feed the NEXT
                   committee. The loop closes; evidence compounds.
```

- **Research** — where ideas enter. Firewalled from the live path; a research script
  can never place an order. Discovery is currently FROZEN (evidence month).
- **Validation** — the gauntlet (`edge_hunt.py --sweep`, `master_backtest.py`,
  `full_yearly.py`). A different agent/model reviews than the one who proposed
  (reviewer-diversity, now literal via the GLM/Qwen bridge). Catches look-ahead,
  post-hoc thresholds, curve-fits.
- **Shadow** — forward evidence with zero risk. Distinguishes "works in history"
  from "still fires as expected today."
- **Committee** — the go/no-go. `evidence_report.py --month-end` →
  [MONTH_1_LIVE_REPORT.md](MONTH_1_LIVE_REPORT.md) + [MONTHLY_EVIDENCE_COMMITTEE.md](MONTHLY_EVIDENCE_COMMITTEE.md).
  Promotes NOTHING automatically; it produces evidence a human acts on.
- **Production** — `live_trader.py` (~1100 lines): session lock → regime fetch →
  per-broker DD-throttle → daily/monthly kill-switch → strategy dispatch. Every
  bracket strategy carries broker-side SL/TP.
- **Evidence** — the output of production (fills, ledger, ops verdict) becomes the
  input to the next committee. Architecture is a loop, not a line.

Deeper: [ARCHITECTURE_AUDIT.md](ARCHITECTURE_AUDIT.md), [LIVE_EXECUTION_FLOW.md](LIVE_EXECUTION_FLOW.md),
[AI_OPERATING_SYSTEM.md](AI_OPERATING_SYSTEM.md).

---

## 3. STRATEGY REGISTER

| Strategy | Purpose | Validated on | Validation status | Production | Expected freq | Known caveats | Evidence | Latest review |
|---|---|---|---|---|---|---|---|---|
| **S1 Asian Sweep** | fade Asian-low sweep + reclaim | QQQ hourly (Alpaca) | YES | LIVE (Alpaca full / MT5 restricted) | ~11/yr (GEX-gated) | MT5 restricted universe | PARITY, VAL_AUDIT | VALIDATION_AUDIT |
| **S2 Gold FVG** | daily gold FVG gap continuation | GLD daily (full_yearly) | FIXED 07-12 (was INERT) | LIVE (clock restarted 07-14) | ~16/yr | hourly variant fired 0/75d; gold weekend gaps ≠ equity | FINDINGS, VAL_AUDIT | VALIDATION_AUDIT |
| **S3 Abnormal Volume** | volume-surge continuation | QQQ daily | PARTIAL (live rule = strict subset ~4/yr vs 15/yr) | LIVE (Alpaca exit path) | ~4/yr live | MT5 no time-exit; harmed by weekend hold | S3_VALIDATION_REVIEW | VALIDATION_AUDIT (KEEP AS-IS to committee) |
| **S4 Multi-Sweep** | dual-index sweep + EMA200 | QQQ+SPY hourly | YES | LIVE | ~55/yr bar-level | archetype of S1 | PARITY, VAL_AUDIT | VALIDATION_AUDIT |
| **S5 ORB** | opening-range breakout | QQQ hourly | PARTIAL on CFD (9:00 bar ≠ auction open) | LIVE | ~50/yr (1.3/day bar-level) | largest weekend gap tail (−4.09% eq worst); benefits from weekend hold | S5_REENTRY, WEEKEND_AUDIT | VALIDATION_AUDIT |
| **OVN Overnight** | overnight close→open drift | QQQ daily | YES | LIVE | ~2/wk | 5% catastrophe stop additive | OVERNIGHT_MOMENTUM_REVIEW | that review |
| **BTC Sweep** | S1 ported to crypto | Binance spot | PARTIAL (venue swap → CFD) | LIVE | ~10–20/yr | validated on Binance, traded on Pepperstone CFD | VAL_AUDIT | VALIDATION_AUDIT |
| **BTCTREND / XSMOM** | crypto trend + cross-sec momentum | ETF/crypto daily | YES (rules) | LIVE — **keep OFF funded** | monthly rebalance | NO broker-side stop | part_c_tsmom | GRAVEYARD_AUDIT |

Machine-readable + full facets: [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md), `knowledge_graph.json`,
`vault/03-Validated-Strategies/`.

---

## 4. RESEARCH GOVERNANCE

| Rule | What it says | Why it exists |
|---|---|---|
| **Clock reset** | Any signal-touching change during the window resets the clean-month clock (verbatim: "any signal-touching change resets the clock"). Reset #1: 07-09 → 07-14 by the S2 fix. | A month is only "clean" if the code didn't change mid-stream. Stops "one quick fix" from laundering an unproven month into a funding decision. See [CLOCK_RESETS.md](CLOCK_RESETS.md). |
| **Freeze** | During the evidence month: no new strategies, infrastructure, or agents. Discovery frozen. | Focus. The only open question is whether the existing edge survives live; more building can't answer it and only adds reset risk. |
| **Committee** | Month-end report is the single go/no-go. Promotes nothing automatically. | One decision point, pre-registered criteria, human-in-the-loop. Prevents drip-promotion on partial data. |
| **Shadow** | New candidates forward-log signals (no orders) until a pre-registered day/rate threshold before any live consideration. | "Works in history" ≠ "fires as expected now." Shadow is free forward evidence. |
| **Validation** | A strategy must pass the gauntlet AND an adversarial review (author ≠ reviewer) before it is anything but an idea. | Look-ahead, post-hoc thresholds, and curve-fits die here (ATR compression, DIX both did). |
| **Graveyard** | Rejected ideas are recorded with reason + evidence + date; never resurrected without NEW evidence. | Memory. Stops re-testing dead ideas (DIX was queued then found already-graveyarded). [RESEARCH_GRAVEYARD_AUDIT.md](RESEARCH_GRAVEYARD_AUDIT.md), FINDINGS.md. |
| **Promotion** | Only a human, post-committee, with green evidence, moves a candidate toward live — and that resets the clock. | Real money is the highest bar; nothing crosses it on autopilot. |
| **Rejection** | Weak/ambiguous evidence → reject, don't argue. Default is NO. | The cost of a false-positive strategy (blown challenge) dwarfs a false-negative (missed edge). |

Governing docs: [NEXT_30_DAY_MONITORING_PLAN.md](NEXT_30_DAY_MONITORING_PLAN.md), [RESEARCH_BACKLOG.md](RESEARCH_BACKLOG.md).

---

## 5. DATA GOVERNANCE

**Datasets** (full trace in [DATA_LINEAGE.md](DATA_LINEAGE.md)): 7-year hourly histories
(`qqq/spy/gld/aapl/msft/nvda/iwm/xlk_hourly_7y.csv`, `multi_etf_hourly.csv`), crypto
(`btc_1h.csv`), fine-grained (`qqq_1min/15min`, `spy_15min`), regime/state
(`state/macro_daily.csv`, `gex_history.csv`, `skew_history.csv`), forward evidence
(`research/results/shadow_signals.csv`, `etf_streams.csv`), execution (`logs/fills.csv`).
Live data comes from broker `get_bars()` at runtime (BAR-COUNT contract).

**Trust boundaries.**
- **Validated** only against the specific dataset in the strategy's register row.
  Cross-dataset generalization is NOT assumed (S2 gold weekend gaps are not inferred
  from QQQ; that would be a category error).
- **Shadowed** = only `shadow_signals.csv` is forward evidence. Everything else is
  backtest history.
- **Executed** = `fills.csv` is the only record of what really happened at a broker.

**Validation limits.** A backtest replays the frozen .csv; live trades a broker feed.
Parity (code matches itself across environments) is verified; validation (code matches
its evidence) is separately audited and has caught drift parity missed.

**Venue differences.** BTC validated on Binance spot, traded on Pepperstone CFD
(basis/spread differ). S5's ORB premise is ETF-true but structurally weaker on the
23-hour NAS100 CFD (no opening auction). Both flagged, both measured via fills — not
guessed.

**Known mismatches (open).** S3 live rule ≠ validated rule (strict subset). S5 CFD-vs-
ETF execution unmeasured until fills accumulate. BTC venue cost unquantified.

---

## 6. OPERATIONS

- **Daily** — the evidence trio (any host): `macro_state.py`, `shadow_etf.py`,
  `daily_check.py`, then `evidence_report.py --daily` → [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md).
  Glance at the dashboard/Telegram. On the VPS: `python status.py` (tasks green).
- **Weekly** — `evidence_report.py --weekly` (Fri): per-stream shadow rates, slippage,
  silent-stream flags.
- **Monthly** — `evidence_report.py --month-end` → the committee report. THE decision.
- **Committee** — human reviews the report against pre-registered criteria; buys
  challenges or stops. Next: **2026-08-16**.
- **Disaster recovery** — everything is in git `main`; the VPS is a clone that
  auto-pulls. To rebuild: clone repo, `cp config.example.ini config.ini` + fill
  secrets, run `setup_vps_git.ps1` (Windows) / schedule tasks. State files
  (`risk_state_*.json`, ledgers) regenerate; only `config.ini` secrets are irreplaceable.
- **VPS** — Windows (ALPHAZONE / 188.190.4.122). `nas100-update` scheduled task pulls
  `main` every 30 min as **SYSTEM** (fixed 07-13 from 0x800710E0 — see [VPS_UPDATE_FIX.md](VPS_UPDATE_FIX.md)).
  Session tasks (`Nas100Bot-*`) run the live sessions with per-venue logs.
- **Dashboard** — `streamlit run dashboard/app.py` → http://localhost:8501 (local,
  read-only, 10-page cockpit, self-explaining strategy cards). Static twin:
  `dashboard/COMMAND_CENTER.md` (`python scripts/ops/command_center.py`).
- **Git** — commit+push on the Mac; VPS pulls within 30 min. Obsidian post-commit hook
  auto-syncs `vault/` (`[bridge-auto]` commits). Token lacks `workflow` scope → the
  operator manages `.github/workflows/*` via the web UI.
- **MT5** — Pepperstone; symbol map QQQ→US100, SPY→US500, GLD→XAUUSD, BTC→BTCUSD;
  atomic SL/TP brackets; server-UTC offset auto-detected. Restricted universe.
- **Telegram** — crash/fill/kill-switch alerts via `alerts.py` (token in gitignored
  `config.ini`). `python status.py --ping` tests it.

**Owed before real money:** rotate the secrets pasted in old chats (readiness blocker).

---

## 7. KNOWLEDGE MAP

The connective tissue is [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md) + `knowledge_graph.json`
(62 nodes / 56 edges: strategies, experiments, reviews, ideas, findings, reports,
dashboard pages, obsidian notes; edges validated_by / reviewed_by / superseded_by /
contradicts / depends_on / feeds / documents / shadowed_by). Regenerate:
`python scripts/build_knowledge_graph.py`.

| To find… | Look in |
|---|---|
| experiments | `research/experiments/*.py`, `research/queue/`, `research/archive/` |
| reviews / audits | `docs/*REVIEW*.md`, `docs/STRATEGY_VALIDATION_AUDIT.md`, `docs/WEEKEND_EXPOSURE_AUDIT.md`, `docs/S5_REENTRY_REVIEW.md` |
| reports | `docs/MONTH_1_LIVE_REPORT.md`, `MONTHLY_EVIDENCE_COMMITTEE.md`, `EVIDENCE_LEDGER.md`, `PROP_READINESS.md` |
| the graveyard | `docs/RESEARCH_GRAVEYARD_AUDIT.md`, `FINDINGS.md` |
| Obsidian notes | `vault/` (03-Validated-Strategies, 08-Incidents, auto/) — navigable via KG backlinks |
| the dashboard | `dashboard/app.py` (interactive) + `dashboard/COMMAND_CENTER.md` (static) |
| what to clean up | `docs/REPO_CLEANUP.md` (recommendations only) |

---

## 8. CURRENT PROJECT STATE

- **Validated & live:** S1, S4, OVN, BTCTREND (YES); S2 (FIXED, own clock from 07-14).
- **Partial / under watch:** S3 (subset drift — KEEP-AS-IS to committee), S5 (CFD
  premise weak — measure via fills), BTC (venue swap — measure via fills).
- **Shadow candidates:** 9-survivor ETF universe (accumulating toward 15-day verdict),
  VIX term-structure gate (WAITING on a backwardation episode).
- **Known blockers (funding gate):** (1) no clean month yet; (2) execution costs
  unmeasured until fills; (3) bracket-close visibility (needs MT5 history export);
  (4) BTCTREND has no broker stop → off funded; (5) secrets rotation owed;
  (6) single-VPS SPOF.
- **Remaining risks:** the edge may not survive live; S5 weekend gap tail; venue
  divergence on BTC/S5-CFD; the whole book is correlated to US equity beta.
- **Next milestone:** the clean evidence window (anchor **2026-07-14**) → **committee
  2026-08-16**. Production is FROZEN until then.

Live detail: [CURRENT_PROJECT_STATE.md](CURRENT_PROJECT_STATE.md) (the operational snapshot).

---

## 9. ROADMAP

**NOW (evidence month — do only this)**
- Let statistics accumulate. Run the daily/weekly evidence cadence.
- Rotate exposed secrets (infra, allowed).
- Confirm the first Alpaca GTC bracket + first MT5 fill show SL/TP correctly.
- Touch NO signal code (resets the clock).

**AFTER EVIDENCE MONTH (post-committee, if green)**
- The committee decision: buy 2–3 parallel FundedNext challenges at config sizing.
- Post-window strategy decisions, each through the pipeline: S3 revert-or-revalidate,
  S5 CFD-vs-ETF execution verdict, S2 first-fills review, BTC venue-cost check.
- The DXY-gate adversarial battery (currently WAITING).
- Repo Phase-2 cleanup ([REPO_CLEANUP.md](REPO_CLEANUP.md)) as one reviewable `git mv` batch.

**LONG TERM**
- Second VPS / redundancy (kill the SPOF) before scaling real capital.
- Broaden the book beyond US-equity beta if evidence warrants (diversification).
- Revisit deferred research only with new evidence (TensorTrade, funding carry,
  industry-rotation TSMOM all currently rejected/deferred for documented reasons).

Only genuinely-useful items are listed; speculative scaffolding is deliberately absent.

---

## 10. LESSONS LEARNED (principles, not just bugs)

1. **Interrogate silence.** Twice, asking "why is X quiet?" found dead code, not
   sparsity — the whole system during the emoji-crash era, and S2 firing 0/75 days.
   A quiet strategy is a hypothesis to test, not a fact to accept.
2. **Timeframe/venue is part of the strategy.** S2's edge was real on daily bars and
   impossible on hourly ones (gaps don't exist intraday). Porting across timeframe,
   venue, or data source can silently break the mechanism. Re-validate on every port.
3. **Parity ≠ validation.** Parity verifies code matches itself across environments;
   validation verifies code still matches its evidence. Three strategies carried drift
   invisible to parity. Run both audit classes.
4. **Adversarial review earns its keep.** ATR compression (look-ahead + post-hoc
   threshold) and DIX (sign-unstable) both looked great and both died under a reviewer
   who was not the author. Default the reviewer to "refute."
5. **CFD financing is a law, not a footnote.** ~3 bps/day on notional kills every
   slow/monthly-hold strategy — re-confirmed 4× (TSMOM, RFS, industry rotation,
   funding carry). Costs must be ON before any verdict.
6. **Operational outages masquerade as bad edges.** "No trades, launched Monday" was
   a Unicode crash and a timezone bug, not a dead strategy. Instrument the plumbing
   (crash hook, fill ledger, ops report) before doubting the signal.
7. **Governance must cost something to be real.** The clock reset pushed the decision
   5 days for a genuine fix — and that pain is the point. A rule you can reinterpret
   away isn't a rule.
8. **Evidence over intuition, every time.** The strongest instinct in the project
   ("the edge feels weak") is answered only by a clean month of live statistics — not
   by more backtests, more strategies, or more conviction. Build the measurement, then
   wait for it.

---

_This constitution supersedes nothing and governs nothing by itself — it points to the
docs that do. Keep it current: when a strategy's status, a governance rule, or the
milestone date changes, update Section 3/4/8 here and the source doc together._
