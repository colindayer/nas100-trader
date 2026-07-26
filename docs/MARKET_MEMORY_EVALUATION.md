# MARKET_MEMORY — evaluated against the complexity rubric

Applying the standard you set: **complexity is a liability that must justify itself with evidence.**
Four questions, answered honestly, before any decision to build.

---

## Finding: half of Market Memory already exists

| Market Memory component | status |
|--|--|
| Today → Macro Regime | ✅ `lab/regime.py` + `events/engine.py::_regime()` tags every event |
| Regime → historical outcomes | ✅ **`query.events(regime=…)` over 2.3M events**, outcomes at 5/10/20/50/100 bars |
| Statistical summary + CI | ✅ `event_study.study()` — mean, hit rate, bootstrap CI, CI-excludes-zero |
| Committee evidence → stored | ✅ `opportunity.py` (supporting *and* contradicting evidence) |
| Trade → outcome | ✅ `position_ledger` + `demo_execution_evidence.jsonl` |
| **Trade → regime linkage** | ❌ **MISSING** — our executions are not tagged with the regime they occurred in |
| **Outcome → lessons** | ❌ **MISSING** — no structured post-trade review record |
| **Historical similarity retrieval** | ❌ **MISSING** — no "today resembles X" query |

**Conclusion: this is not a new subsystem. It is one missing join plus a query layer.**

---

## Q1 — What measurable problem does it solve?

**Real problem:** post-trade review currently has no comparison base. When a trade loses, we cannot
ask *"what normally happens in this regime?"* — so every outcome is interpreted in isolation, which
is how single results get over-read in both directions.

**Measurable form:** for any current regime, produce the historical base rate of outcomes with a
confidence interval, and the count of comparable observations.

**Not a real problem:** predicting tomorrow. Market Memory must not become a forecaster.

## Q2 — What evidence shows the existing architecture cannot solve it?

**Mostly it can.** `query.events(regime="up/highvol")` + `event_study.study()` already answers
*"what happened historically in this regime?"* with a bootstrap CI over a 2.3M-event database.

The genuine gap is narrow and specific: **our own trades carry no regime tag**, so we cannot ask
*"how did WE do in this regime?"* — only *"what did the market do?"*.

**Honest verdict: Q2 justifies a field addition and a query, not a subsystem.**

## Q3 — How will we measure whether it improved the platform?

This is where the proposal is weakest, and it must be answered before building.

**Proposed metric:** *post-trade review completeness* — the share of trades whose review cites a
historical base rate with n and CI, rather than a narrative. Target 100%. Measurable, falsifiable.

**Rejected metric:** "better decisions." Unfalsifiable at ~100 trades/year.

**If Market Memory ever feeds a pre-trade decision**, it must first pass the Trial Registry as a
hypothesis: *does regime-conditioned historical outcome improve walk-forward P(positive)?* Our prior
is poor — PHASE 510 found regime/timeframe context added AUC ≈ 0.50.

## Q4 — Can we remove it if it fails?

**Yes, if and only if it is read-only.** A query layer over existing stores can be deleted without
consequence. It becomes unremovable the moment a decision depends on it.

**Design constraint: Market Memory may be read by humans and by post-trade review. It may not be
read by `authorize()`, the Belief Graph, or any sizing logic.**

---

## The statistical objection — the analogue fallacy

> *"This regime resembles 2025-08-14, confidence 83%. Outcome: 6 trades, +2.1R"*

**This specific form should not be built.** Three problems:

1. **n = 1.** Six trades on one historical day is not evidence of anything. Nearest-neighbour
   matching on a high-dimensional regime vector with small n retrieves noise reliably.
2. **"Confidence 83%" is undefined.** It is a *similarity* score, not a probability of any outcome —
   yet it will be read as one. This platform has already made that error once: I reported a 48.8%
   pass rate that was really a selection-biased maximum.
3. **Similarity is unbounded in specification.** Every regime resembles some past day at some
   threshold. Without a pre-registered distance metric and a minimum-n rule, it always returns an
   answer, which makes it unfalsifiable.

### The defensible form
> *"Current regime: down/highvol. **412 comparable historical observations.** Market outcome at
> 20 bars: mean −0.03%, 95% CI [−0.11%, +0.05%] — **CI includes zero.** Our own trades in this
> regime: 0 (insufficient). Contradicting: liquidity is thinner than the historical comparison set."*

Base rates over **many** observations with a CI and an explicit n — never a single analogue, never a
bare confidence number. This is exactly what `event_study.study()` already returns.

---

## Recommendation

**BUILD — minimally, and not yet.**

Scope, in priority order:
1. **Tag every execution with its regime at entry.** One field on `TradeExecutionRecord`. Trivial,
   and without it nothing else is possible. **Do this before Phase C** so the demo campaign captures
   it from trade one — retrofitting is impossible.
2. **Add a `lessons` field to the post-trade review** — human-written, structured.
3. **A read-only `market_memory.similar(regime)` query** wrapping `query.events` + `event_study`,
   returning base rate + n + CI. **After** 30+ demo trades exist, not before.

**Do not build:** a separate memory store (duplicates the Event DB), a similarity/confidence score,
or any path from memory into a trading decision.

**Sequencing:** item 1 belongs in Phase A/B prep. Items 2–3 belong after Phase C has produced data.
Building a memory system before there are memories worth having is the same error as deploying a
strategy before its trial.

---

## Applying the rubric backwards — where the existing architecture already fails it

Consistency demands the same test on what is already built:

| subsystem | Q1 problem | Q2 evidence | Q3 metric | Q4 removable | verdict |
|--|--|--|--|--|--|
| `safety_state` | caps defeated by restart | V-01/02 reproduced | restart tests | no (correctly) | **JUSTIFIED** |
| `startup_reconciler` | orphans undetected | the BTC incident | 5 detections | no | **JUSTIFIED** |
| Contract signing | disk edit = LIVE_APPROVED | V-03 reproduced | tamper tests | yes | **JUSTIFIED** |
| Belief Graph v2 | circular dependency | deadlock demonstrated | promotion states | no | **JUSTIFIED** |
| `tradingview_bridge` | none demonstrated | — | none | yes | **FAILS — remove or shelve** |
| `telegram_notifier` | real (no alerting) | 02:00 halt unnoticed | alert delivery | yes | **JUSTIFIED but UNWIRED — finish or delete** |
| `market_intel/engine.py` | opportunities in prod | none — no runner calls it | none | yes | **FAILS — unused** |
| `prop_objective.py` | prop survival at order time | not wired | none | yes | **FAILS — unused** |
| `belief_reader` (v1) | superseded by v2 | duplicate logic | none | yes | **FAILS — retire** |
| `gsr_strategy.py` | none | unreachable | none | yes | **FAILS — delete** |

**Five existing components fail the rubric.** By the standard you just set, the next action is not
adding Market Memory — it is **removing or finishing those five.** Deleting dead code is the cheapest
reliability improvement available, and it shrinks the surface that must be verified for 60 days.

---

## Revised priority

| # | action | rationale |
|--|--|--|
| 1 | **Wire alerting** (`telegram_notifier`) | unattended operation is impossible without it |
| 2 | **Delete/shelve the 4 failing components** | complexity with no justification; shrinks the 60-day surface |
| 3 | **Add regime tag to `TradeExecutionRecord`** | must precede Phase C or the data is lost forever |
| 4 | Phase A deploy → Phase B shadow → Phase C demo | per the validation plan |
| 5 | Market Memory query layer | only after ≥30 demo trades exist |
| 6 | Evidence Panel (independent generators) | your redesign — correct, but after operations are proven |

**The Evidence Panel structure you proposed is right** — Calendar / Macro / Cross-Asset / Execution
Quality / Market Structure / Research, each an independent generator, combined by the Belief Graph.
That is statistically defensible in a way bull-vs-bear debate is not. It is also **entirely
implementable as extensions of existing modules**, which is the strongest argument for it.
