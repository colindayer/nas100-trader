# QUANT_OS_ARCHITECTURE

Design document. No code written. Architecture over implementation.

**Governing constraint:** ten of the twelve proposed subsystems already exist in some form. This
document recommends **extension over creation** in every such case, and rejects outright the parts
that would add complexity without adding information.

---

## 0. CRITICAL EVALUATION OF THE PROVIDED CONCEPTS

You asked me to treat these as inspiration, not truth. Evaluated on evidence, not appeal.

| concept | verdict | reasoning |
|--|--|--|
| **Hard trade caps** | **ADOPT — already built** | `LimitedDemoEnvelope` + persistent `safety_state`. The single highest-value control in the system. |
| **Persistent risk gates** | **ADOPT — already built** | V-01/02/04 closed. This is what separates a desk from a bot. |
| **AI proposes / Rules dispose** | **ADOPT — already the architecture** | `authorize()` is a rules engine; no model output can bypass it. Keep this inviolable. |
| **Guardrail checklist** | **ADOPT** | Extends `healthcheck.py`. Cheap, high value. |
| **Macro News Radar** | **ADOPT WITH LIMITS** | Genuinely useful as *context*. Must never emit signals. See §10. |
| **Macro Engine** | **EXTEND `lab/regime.py`** | Do not build new. Regime classification exists. |
| **Committee / Bull-vs-Bear debate** | **REJECT AS SPECIFIED — REDESIGN** | See below. This is the most important judgement in the document. |
| **VWAP + ADX concepts** | **NEUTRAL — must enter Trial Registry** | Two indicators among thousands. No prior. Treat exactly like ICT/SMC. |
| **Futures-based macro observation** | **EVALUATE ONLY** | See §9. Our own cross-asset study says the prior is weak. |
| **Social signals (Reddit/Telegram)** | **REJECT** | Violates your own First Principle. See below. |
| **News aggregation** | **ADOPT** | With source attribution and dedup. See §10. |
| **Institutional workflow examples** | **ADOPT selectively** | The *artefacts* (pre-trade memo, post-trade review) are valuable; the org chart is not. |

### Why the Committee/Debate architecture is rejected as specified

A Bull Analyst and a Bear Analyst reading **the same data** produce **zero incremental information**.
Debate feels like rigour, but adversarial argument over a shared evidence set is theatre: it can
change confidence without changing information. Two failure modes follow directly:

1. **Manufactured confidence.** A vote of 5–2 looks decisive but may reflect one data source counted
   five times. Committee agreement is *not* independent confirmation.
2. **Laundering.** "The committee voted BUY" becomes a justification that obscures the fact that no
   member had an edge. This is exactly how the 404/ICT material sounds authoritative.

There is no evidence in the literature that multi-agent LLM debate improves financial forecasting.
Our own results are directly relevant: **higher-timeframe "confirmation" added AUC ≈ 0.50** (PHASE
510) — a second opinion on the same price series added nothing measurable. A committee is the same
mistake at a higher level of abstraction.

**Redesign — Evidence Panel, not Committee.** Keep the structure, remove the debate:
- Each member is an **independent evidence channel**, valuable *only* if it reads a source no other
  member reads. If two members share a source, one is deleted.
- Members emit **evidence with provenance and uncertainty**, never a directional vote.
- **Disagreement is recorded as an output, not resolved by vote.** Contradiction is information;
  averaging destroys it.
- Aggregation is the **Belief Graph** (Bayesian, already built), not a show of hands.

### Why social signals are rejected

Your First Principle says *"never copy social-media trading ideas."* Reddit/Telegram sentiment is the
same substance one layer removed — it is the *aggregate* of those ideas. It carries: severe
selection bias (losers post less), reflexivity, trivial manipulability, and ToS/scraping exposure.
If it is ever revisited, it enters as a **pre-registered hypothesis in the Trial Registry**, like
anything else — never as a live input.

---

## 1. HIGH-LEVEL ARCHITECTURE

```
┌──────────────────── RESEARCH PLANE (~/research-lab) ────────────────────┐
│  Trial Registry · Event DB (2.3M) · Walk-forward · Scorecard · GT-Score │
│  ALL external ideas enter HERE. Nothing reaches execution un-tested.    │
└────────────────────────────────┬────────────────────────────────────────┘
                    signed artefacts only (belief snapshot, contracts)
                                 ▼
┌──────────────────── EVIDENCE PLANE (market_intel/, extended) ───────────┐
│  Providers → Normaliser → MACRO BOARD ─┐                                │
│  (calendar, prices, rates, vol, news)  ├→ EVIDENCE MODEL (provenance,   │
│                        MICRO BOARD ────┘   confidence, contradiction)   │
│  READ-ONLY. Structurally incapable of placing an order.                 │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ▼
┌──────────────────── DECISION PLANE (execution_safety/) ─────────────────┐
│  Belief Graph v2 (Research ⟂ Operational)                               │
│         ↓                                                               │
│  Promotion Pipeline (5 states)                                          │
│         ↓                                                               │
│  GUARDIAN — sole authority; overrides any confidence                    │
│         ↓                                                               │
│  authorize() — 10 fail-closed gates → OrderIntent                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ▼
┌──────────────────── EXECUTION PLANE ────────────────────────────────────┐
│  execution_guard (one-shot) → broker (+ mandatory SL) → ledger          │
│         ↓                                                               │
│  Reconciliation → Operational Evidence → back to Belief (capped)        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Four planes, one direction.** Evidence never becomes an order without traversing the Decision
Plane. The Research Plane is upstream of everything and never live.

---

## 2. MACRO BOARD — extends `lab/regime.py`

**Do not build new.** `regime.classify()` already emits trend / volatility / liquidity / risk-on-off.
Extend it with: rates & yield curve, dollar, commodities, crypto, central-bank calendar proximity.

**Every statement carries a claim record:**
```
claim:        "Regime = risk-off"
evidence:     [VIX_percentile=0.82(FRED), DXY>50dma(MT5), yield_curve=-0.4(FRED)]
confidence:   0.61            # from evidence count × source independence × recency
contradicts:  [equity_indices_at_highs]
unknown:      [positioning — no COT source wired]
as_of:        2026-07-25T13:00Z
staleness:    calendar 8m, prices 30s
```

Three rules, all learned from this project's failures:
1. **No claim without evidence.** A dashboard line with no source is a hardcoded status string — the
   exact defect found in `dashboard.py` ("GUARDIAN: not wired" printed *after* it was wired).
2. **Contradictions are displayed, never resolved.** Resolving them silently is where narrative
   replaces measurement.
3. **Unknowns are enumerated.** Absence of a source is a first-class output.

## 3. MICRO BOARD — extends `market_intel/state.py`

Already emits 14 fields (trend, ATR percentile, session, kill zones, structure, sweep, FVG, OB, VWAP,
S/R). **Add only:** spread quality, realised liquidity, rolling cross-instrument correlation.

**Constraint honoured: no BUY/SELL.** `state.py` already emits no direction. Preserve absolutely —
the moment the Micro Board emits a direction, it becomes a strategy and must enter the Trial Registry.

---

## 4. EVIDENCE PANEL — extends `market_intel/opportunity.py`

Replaces the proposed Committee. Members, each defined by a **source no other member reads**:

| member | exclusive source | emits |
|--|--|--|
| Macro | calendar, rates, FRED | regime claims + confidence |
| Micro | MT5 price/structure | structural claims |
| News | News Radar | tagged, deduplicated events |
| Execution | broker telemetry (spread, slippage, latency) | tradeability |
| Risk Officer | Guardian + safety state | binding constraints |
| Research Officer | Belief Graph + Trial Registry | prior strength |

- **No member votes. No member trades.** Members emit evidence records.
- Two members sharing a source ⇒ delete one. Redundancy is mistaken for confirmation.
- Output is an `Opportunity` (already exists) carrying **supporting AND contradicting** evidence.

## 5. VERDICT ENGINE — extends `promotion_pipeline_v2` + `authorize()`

Verdicts: `TRADE · WAIT · NO_TRADE · MORE_EVIDENCE · UNKNOWN`.
**`BUY`/`SELL` deliberately excluded** — direction comes from an approved strategy contract, not from
a verdict. This prevents the panel becoming a discretionary trader.

`UNKNOWN` and `MORE_EVIDENCE` are **first-class, not failures**. Given this project's history, most
verdicts should be `NO_TRADE`. Every verdict is appended immutably with its full evidence set.

## 6. GUARDIAN — unchanged, authority reaffirmed

**Guardian ignores committee confidence entirely.** Already architecturally true: `authorize()`
blocks on any single gate failure, and no confidence score is an input to a gate. Extension:
Guardian must also read `safety_state` (halt, daily count, drawdown baselines) — done in V-01/02/04.

**Non-negotiable:** unanimous panel agreement plus Guardian veto = **NO TRADE**. There is no
override, no quorum that outranks it, and no configuration exposing one.

## 7. EVIDENCE ENGINE — extends `operational_belief` + `position_ledger`

Per-trade record already specified in `TradeExecutionRecord` (expected/actual entry, spread,
slippage, latency, retcode, stop verified, reconciliation). **Add:** macro state snapshot, news
state, panel evidence for/against, verdict, belief values, Guardian decision, outcome, post-trade
review.

**Caution on "this becomes training data."** With ~100 trades/year it is *audit* data, not training
data. Fitting a model to a few hundred confounded observations is precisely the overfitting this
platform exists to prevent. Its value is explainability and incident forensics.

## 8. RESEARCH ENGINE — already exists, enforce universally

`lab/governance.py` Trial Registry + pre-registration + scorecard + walk-forward + GT-Score.
**VWAP, ADX, ICT, SMC, order flow, futures, news, and the Evidence Panel itself** all enter here.
No new subsystem. The gap is enforcement, not capability: nothing currently *requires* a trial before
a contract can be written. **Recommendation:** `authorize()` should reject a contract whose
`approved_trial_ids` do not resolve to a passing scorecard — closing the last governance gap.

## 9. FUTURES DATA — recommendation: **DO NOT ADD YET**

Evidence against, from our own work: PHASE 520 ran 49 cross-asset experiments; **1 robust hit with
incremental AUC +0.023** — information, not edge. PHASE 510: higher-timeframe context AUC ≈ 0.50.
The prior that "more cross-asset series improves detection" is empirically weak *in this system*.

Cost is real: CME data licensing, contract-roll handling, a new provider surface, more failure modes.

**Recommendation:** one pre-registered study — *does adding CME rates/DXY futures improve regime
classification accuracy versus the current spot proxies?* — with a pass bar of a materially better
AUC across walk-forward folds. Adopt only on a pass. **Do not integrate first and evaluate later.**

## 10. NEWS RADAR — new, but narrowly scoped

The only genuinely new subsystem recommended. Architecture inferred, not copied:

```
Sources (licensed/public feeds, RSS, official releases)
   ↓ fetch with provenance (url, publisher, fetched_at, licence)
   ↓ DEDUPLICATE   near-duplicate clustering; one event, many reports
   ↓ ENTITY EXTRACT instrument / currency / central bank / indicator
   ↓ MACRO TAG      inflation | growth | policy | liquidity | geopolitical
   ↓ RELIABILITY    per-source score from HISTORICAL accuracy, not reputation
   ↓ CROSS-VALIDATE ≥2 independent sources before a claim is "confirmed"
   ↓ IMPACT         from MEASURED historical reaction (reaction_recorder), never assumed
   ↓ STORE          immutable, queryable
```

Hard constraints:
- **Emits evidence, never signals.** Same rule as the Micro Board.
- **Reliability is measured, not assigned.** A source is credible because its past claims verified.
- **Impact is measured.** `reaction_recorder` already collects post-release moves — that is the only
  legitimate basis for an impact score. Until it has data, impact is `UNKNOWN`.
- **No scraping against ToS.** Same discipline as the Forex Factory decision.

## 11. OBSERVABILITY — the pre-trade memo

Every trade must answer eleven questions **before** submission, stored with the intent:

*Why? Why now? Why not earlier? Why this size? Why not larger? Why not smaller? Why this stop?
Why did Guardian approve? Why did Belief agree? Why did the panel disagree? What would have
prevented this trade?*

If any answer is unavailable, the verdict is `MORE_EVIDENCE` — not a trade with a missing rationale.
Post-trade, the same record gains outcome and review. **This is the artefact worth borrowing from
institutional workflow** — not the org chart.

## 12. PRODUCTION READINESS — 24/7 for months

The architectural mismatch is already identified and fixed at the state layer: **the deployment is a
scheduled one-shot; the safety model must therefore be on disk.** Every control that spans
invocations is persisted, versioned, checksummed, atomic, locked, and fails closed (V-01/02/04/05/06,
112 tests).

Still missing for genuine unattended operation:
1. **Alerting.** `telegram_notifier` has **zero callers**. A halt at 02:00 sits unnoticed. This is the
   single largest gap for autonomous running.
2. **Exit reconciliation.** Entries are verified meticulously; exits are not watched at all.
3. **Runtime deployment enforcement** (V-13) — no runner refuses to start on `INCOMPLETE`.
4. **Watchdog.** Nothing detects "the scheduled task stopped running."

---

## 13. OPERATIONAL STATE MACHINE

```
BOOT → SELF_TEST → LOAD_STATE → RECONCILE → LOAD_GOVERNANCE
                                    │
                              (fail) └→ HALTED ──(human clear_halt)──┐
                                                                      │
EVIDENCE → PANEL → VERDICT → AUTHORIZE → EXECUTE → POST_TRADE → PERSIST → SLEEP
```
Every transition: **precondition · postcondition · rollback · failure = HALT (never proceed).**
`HALTED` is absorbing — exit requires a named human. Already implemented in `safety_state`.

## 14. ROADMAP (dependency-ordered)

| # | milestone | exit criteria |
|--|--|--|
| 1 | **Alerting wired** | every halt/critical/fill emits an alert; proven by an induced halt |
| 2 | **Exit reconciliation** | `exit_verified` can be true; exits reconciled |
| 3 | **Demo evidence campaign** | 30 fully-evidenced trades, 0 orphans, ≥1 real restart survived |
| 4 | **Macro/Micro Board extension** | every claim carries evidence + contradictions + unknowns |
| 5 | **News Radar** | dedup + attribution + *measured* reliability, evidence-only |
| 6 | **Evidence Panel** | independent channels; disagreement recorded, not voted away |
| 7 | **Futures study** | pre-registered; adopt only on a pass |
| 8 | **100-trade live-readiness evidence** | per `EVIDENCE_FRAMEWORK.md` |

**Milestones 1–3 are worth more than 4–8 combined.** Nothing in the evidence layer matters while a
2 AM halt goes unnoticed.

---

## WHAT WOULD A TOP-TIER SYSTEMATIC HEDGE FUND BUILD DIFFERENTLY?

**1. They would not build this at all — they'd buy the boring parts.** OMS, EMS, market data,
reconciliation, TCA are commodity infrastructure. We have spent weeks rebuilding a bad OMS. A fund
buys it and spends 100% of its scarce attention on alpha.

**2. Research and production would share one codebase.** Our firewall prevents research reaching
production — *including its negative findings*. That is precisely how a sweep strategy traded live
while the research had rejected it six times. A fund runs the *same* signal code in backtest and
production; divergence is a bug, not an architecture.

**3. Capital allocation would be portfolio-level, continuous, and optimal.** We size per-strategy
with fixed fractions. A fund solves a portfolio problem across all strategies simultaneously with
covariance, capacity, and turnover constraints.

**4. Execution would be a measured discipline.** TCA against arrival price, participation limits,
venue analysis, market-impact models. We market-order into NFP and hope. Our entire execution
knowledge is "spreads widen" — unquantified.

**5. They would have killed this strategy already.** ~0.62 Sharpe, one asset class, no capacity
analysis, ~100 trades/year. At a fund this is not a strategy — it is a *candidate* that fails the
capital-allocation bar on Sharpe, breadth and capacity simultaneously.

**6. Independent risk.** Risk reports to the CRO, not to the person who wrote the strategy. Here the
same author wrote the strategy, the Guardian, and the tests that pass them. **The most serious
structural weakness in this platform is that I am marking my own homework** — evidenced by a TOCTOU
race in my own safety fix that my own tests passed.

**7. Breadth over depth.** A fund runs dozens of low-correlation strategies across asset classes.
Our sharpest finding — diversification lifted combined Sharpe above every sleeve — is the same
principle at a tenth of the scale.

### Where this architecture still falls short

1. **No independent verification.** Single author, single reviewer. Structural, not fixable by more tests.
2. **Never executed an order.** Every guarantee is mock-proven.
3. **No alerting.** Disqualifying for unattended operation.
4. **No exit discipline.** Half a trade lifecycle is unmonitored.
5. **No capacity or TCA model.** We cannot answer "how much can this take?" or "what did execution cost?"
6. **Evidence volume too low for its ambitions.** A Panel + News Radar + Belief Graph over ~100
   trades/year risks a rigorous-looking apparatus fitted to noise. **The apparatus must stay simpler
   than the evidence supporting it** — currently the reverse is true.
7. **The edge remains marginal.** No architecture converts 0.62 Sharpe into a business. Elegance
   here is a way of *not losing money to operational failure* — it is not alpha.

**Final judgement:** the governance is genuinely strong and unusual for a retail system. The
architecture proposed above is directionally right but **larger than the evidence justifies**. Build
milestones 1–3. Defer 4–8 until 100 clean trades exist. **Complexity added before evidence is the
same error as a strategy deployed before a trial.**
