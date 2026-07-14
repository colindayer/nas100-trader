# RESEARCH LAB — architecture v2 (Phase 1: design for approval)

_2026-07-14. DESIGN ONLY — no implementation until approved. A SEPARATE, world-class
quantitative research platform alongside frozen production. Firewall absolute. Optimizes
for MAXIMUM idea generation / validation / robustness / evidence — not for recreating
Vibe-Trading. Rejects duplicate INFRASTRUCTURE; embraces every research CAPABILITY._

## 0. Framework vs Capability (the governing principle)
| REJECT — duplicate infrastructure (production already provides) | EMBRACE — research capability (build to world-class depth) |
|---|---|
| execution engine / order routing | large, extensible factor library |
| broker integrations (MT5/Alpaca/Binance) | multiple data vendors + alternative datasets |
| production dashboard | benchmark engine |
| production risk / kill-switches / DD-throttle | robustness: bootstrap CI / Monte-Carlo / permutation / sensitivity / stability |
| deployment stack (VPS tasks, evidence bridge) | hypothesis registry + experiment tracking + reproducible run cards |
| a second live-trading system | multi-LLM reviewer panel · MCP integration |
| — | literature ingestion / academic paper mining |
| — | automated idea generation · feature engineering · factor discovery |
| — | research knowledge graph |
Research reuses production's proven parts ONLY as **read-only inputs or patterns**
(price snapshots, the Research-OS governance shape, the local LLM bridge) — never imports
its code.

## 1. The firewall (non-negotiable, enforced)
```
~/Trading/
  nas100-trader/   PRODUCTION (frozen, single source of truth) — never imports research
  research-lab/    RESEARCH (new repo) — never executes trades
```
- Research imports NOTHING from production; contains NO broker/order/risk-execution code.
- **CI firewall test** greps the tree and FAILS on `order_send|place_order|import MetaTrader5|
  broker|risk_state|kill.?switch` — research literally cannot trade.
- Only bridge to production is a HUMAN moving a "Live Candidate" into production's existing
  Research-OS queue, which then obeys production's shadow/committee/clock governance.
- Data is one-way: production price CSVs are COPIED (hash-stamped snapshots) into
  `research-lab/data/`; research reads no live feed.

## 2. Folder structure
```
research-lab/
  data/
    vendors/         multi-vendor loaders + fallback chain (yfinance, Stooq, Tiingo, FMP,
                     AlphaVantage, Polygon, CCXT/crypto, FRED/macro, ...) -- read-only
    altdata/         alt-data adapters (options/GEX, sentiment, positioning, calendar)
    quality/         data-quality gate + reports
    snapshots/       hash-stamped frozen inputs (reproducibility)
  lab/
    dataquality/     missing/dup/OHLC/timestamp/NaN/session-gap/corporate-action checks
    registry/        hypothesis registry (ID/desc/author/date/status/lineage)
    engine/          research backtest core (vectorized + event; NO broker)
    experiments/     runner: grid / walk-forward / CV / rolling / purged-KFold / sweeps
    validation/      bootstrap CI · Monte-Carlo · permutation · sensitivity · stability · DSR/PBO
    benchmark/       vs Buy&Hold / QQQ / NDX / prop-target / risk-free / factor benchmarks
    factors/         LARGE modular factor library (families + plug-in `@factor`), IC/decay tooling
    discovery/       factor discovery + feature engineering + automated idea generation
    reviewers/       multi-LLM reviewer panel (Qwen/GLM/Claude) — reviewer-diversity voting
    literature/      paper mining (arXiv/SSRN) -> hypotheses -> registry
    kg/              research knowledge graph (factors↔ideas↔experiments↔papers↔regimes↔results)
    reporting/       markdown notebooks + charts + run_card.json
    nl/              natural-language -> ExperimentSpec (LLM, human-confirmed)
    mcp/             MCP: expose research tools + consume external MCP data tools
  experiments/       run artifacts (one dir per run)
  registry/ideas/    one file per hypothesis
  dashboard/app.py   SEPARATE research dashboard (port 8502) — NOT the production one
  cli.py             lab research/run/promote/mine/discover/review
  tests/             incl. firewall test
```

## 3. Capability depth (how each goes BEYOND a minimal version)
- **Factor library** — not "small," not "461 hardcoded": a *taxonomy* (trend, momentum,
  volatility, mean-reversion, breadth/internals, seasonality, calendar, macro, microstructure,
  options-derived) with a plug-in `@factor` registry that scales to hundreds+, each with
  PIT-safety, IC/IR, decay and orthogonalization tooling. Grows unbounded; stays modular.
- **Data** — a multi-vendor layer with an intelligent fallback chain + per-vendor quality
  scoring + alt-data adapters; every load hash-stamped for reproducibility.
- **Robustness** — the full battery: bootstrap CI, Monte-Carlo path/resample, permutation
  (shuffled-label & random-entry nulls), sensitivity, parameter-stability surfaces, and
  overfitting metrics (Deflated Sharpe, Probability of Backtest Overfitting).
- **Reviewer panel** — multiple LLMs review each candidate on DIFFERENT lenses (Qwen:
  extraction/repro; GLM: literature/stats; Claude: final adjudication) with reviewer≠author
  and a majority/veto rule. Reuses the existing local bridge; adds no API providers you lack.
- **Literature mining** — pull papers, extract testable hypotheses + reported effect sizes,
  auto-register them, and cross-check the KG so nothing already-graveyarded is re-proposed.
- **Automated idea generation** — proposes hypotheses from (factor combinations × literature
  × regime gaps × past graveyard), scored and DEDUPed against the KG; ALWAYS human-gated
  before a run. Volume of ideas up; false-discovery controlled by the validation battery.
- **Knowledge graph** — extends your production `knowledge_graph.json` idea to research:
  links every factor, hypothesis, experiment, paper, regime and result, powering discovery,
  dedup, and "what's promising / what's dead."
- **MCP** — the lab both exposes its tools over MCP and consumes external MCP data tools,
  so the platform is scriptable and extensible without a bespoke API server.

## 4. Data flow
```
literature mining + factor library + KG + regime gaps
     -> automated idea generation (scored, deduped) --[HUMAN GATE]-->
NL / manual ExperimentSpec
     -> data-quality gate (bad data -> stop)
     -> experiment runner (grid / walk-forward / purged-CV / sweeps)
     -> robustness battery (bootstrap/MC/permutation/sensitivity/stability/DSR/PBO)
     -> benchmark engine (QQQ/NDX/buy&hold/prop-target/rf)
     -> multi-LLM reviewer panel (diverse lenses, reviewer≠author, veto)
     -> reporting (report.md + run_card.json + charts) + registry status + KG update
     -> [HUMAN REVIEW] -> Live Candidate -> production Research-OS queue (prod governs from here)
```
Every run's `run_card.json` (spec hash, data-snapshot hash, seed, git commit, full metrics)
makes every result reproducible.

## 5. Promotion pipeline (unchanged firewall)
`Research → Validation → Walk-Forward → Shadow → HUMAN REVIEW → Production`.
The Lab owns Research→Validation→Walk-Forward and produces the Shadow SPEC; it STOPS at a
human-reviewed Live Candidate. Production's existing shadow/committee/clock-reset pipeline
owns everything downstream. The Lab never promotes.

## 6. Feature ranking & phased build
| capability | Research Value | Impl Cost | Complexity | Impact | Phase |
|---|---|---|---|---|---|
| Data layer (multi-vendor) + data-quality gate | HIGH | MED | MED | HIGH | **A — foundations** |
| Research engine + experiment runner (grid/WF/CV) | HIGH | MED | MED | HIGH | **A** |
| Hypothesis registry + reproducible run cards | HIGH | LOW | LOW | HIGH | **A** |
| Robustness battery (bootstrap/MC/perm/sens/stability/DSR/PBO) | VERY HIGH | MED | MED-HIGH | VERY HIGH | **B — evidence** |
| Benchmark engine | MED-HIGH | LOW | LOW | MED-HIGH | **B** |
| Factor library (large, modular) + IC/decay tooling | HIGH | MED-HIGH | MED | HIGH | **C — discovery** |
| Feature engineering + factor discovery | HIGH | HIGH | HIGH | HIGH | **C** |
| Research knowledge graph | HIGH | MED | MED | HIGH | **D — intelligence** |
| Multi-LLM reviewer panel | MED-HIGH | MED | MED | HIGH (quality/dedup) | **D** |
| Literature ingestion / paper mining | MED-HIGH | MED | MED | MED-HIGH | **D** |
| Automated idea generation | HIGH | MED-HIGH | HIGH | HIGH (throughput) | **D** |
| MCP integration | MED | MED | MED | MED (extensibility) | **D** |
| NL research interface | MED | MED | MED-HIGH | MED (UX) | **D** |
| Research dashboard (separate :8502) | MED | MED | MED | MED | **D** |

**Phase A** is the bedrock everything else stands on (data + engine + registry +
reproducibility). **Phase B** makes results trustworthy (the robustness/evidence edge that
makes this better than a naive backtester). **Phase C** supplies ideas at scale (factors +
discovery). **Phase D** is the intelligence layer (KG + reviewer panel + literature +
auto-ideas + MCP + NL + dashboard) that turns it into a self-compounding research desk.

## 7. What we still do NOT build (framework only)
React frontend · FastAPI backend · Docker stack · any broker/execution/order code · a
second risk engine · a duplicate production dashboard · a second live-trading system ·
new LLM API providers (reuse the local Qwen/GLM bridge; Claude as adjudicator). Capability
is unbounded; infrastructure is not duplicated.

## Approval gate
This is the Phase-1 architecture v2. **No code until you approve.** Suggested first slice:
**Phase A** (data + quality + engine + runner + registry + run cards) — the reproducible
foundation — with the CI firewall test from commit one. Then B (robustness) delivers the
world-class evidence layer. Confirm scope/phasing and I begin Phase A in the new repo,
production untouched.
