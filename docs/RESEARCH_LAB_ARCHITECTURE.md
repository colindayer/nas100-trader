# RESEARCH LAB — architecture (Phase 1: design for approval)

_2026-07-14. DESIGN ONLY — no implementation until approved. A SEPARATE research
system alongside production. Production stays frozen and is the single source of
truth. Borrows IDEAS from HKUDS/Vibe-Trading (data-quality, validation robustness,
modular factors, benchmarking, NL→experiment, run cards); rejects its framework
(React/FastAPI/Docker/13-LLM/broker engines/execution/swarm)._

## 0. The firewall (non-negotiable)
```
~/Trading/
  nas100-trader/     PRODUCTION (frozen)   -- never imports research
  research-lab/      RESEARCH (new repo)    -- never executes trades
```
- **Research imports NOTHING from production** (no live_trader/broker/mt5/risk).
- **Research contains NO broker, order, or risk-execution code.** A CI test greps the
  tree and FAILS the build if it finds `order_send`, `place_order`, `import MetaTrader5`,
  `import.*broker`, or any live-trading symbol.
- **Only bridge between the two is a HUMAN.** A research "Live Candidate" is hand-carried
  into production's existing Research-OS queue; research code never writes to production.
- Data flows one way: production's frozen price CSVs are COPIED (read-only snapshots)
  into `research-lab/data/`; research never reads a live broker feed.

## 1. Folder structure
```
research-lab/
  README.md  ARCHITECTURE.md  pyproject.toml
  data/
    prices/          read-only snapshots (qqq_hourly_7y.csv, ...) copied from prod
    quality/         data-quality reports (generated)
  lab/                         the library (pure, importable, no side effects)
    dataquality/     missing/dup/OHLC/timestamp/NaN/session-gap checks  (build #1)
    registry/        idea registry: ID/desc/author/date/status          (build #2)
    engine/          SIMPLE research backtest core (vectorized; NO broker) (build #3)
    experiments/     runner: grid, walk-forward, CV, rolling, sweeps      (build #3)
    validation/      bootstrap CI, Monte Carlo, permutation, sensitivity, stability (#4)
    benchmark/       vs Buy&Hold / QQQ / NASDAQ / prop-target / risk-free (#5)
    reporting/       markdown notebook + charts + run_card.json          (#6)
    factors/         modular factor plugins (trend/vol/breadth/season/macro) (#7)
    nl/              natural-language -> structured experiment spec       (#9)
  experiments/       run artifacts, one dir per run (spec/results/report/charts)
  registry/ideas/    one markdown+frontmatter file per hypothesis
  dashboard/app.py   SEPARATE Streamlit research dashboard (port 8502)    (#8)
  cli.py             `lab research "..."`, `lab run EXP-...`, `lab promote ...`
  tests/             incl. the firewall test (no trading symbols)
```

## 2. Modules & interfaces (what each exposes)
| module | interface | reuses |
|---|---|---|
| `dataquality` | `check(df) -> QualityReport(ok, issues[])` | Vibe idea; new code |
| `registry` | `Idea(id,desc,author,date,status)`; `create/advance/list` | your **Research-OS pattern** (ideas/experiments/graveyard) |
| `engine` | `run(signals_df, prices, costs) -> equity, trades` | your validated engine *pattern* (re-implemented, no broker) |
| `experiments` | `ExperimentSpec` -> `Result(metrics, folds, artifacts)` | grid/WF/CV — Vibe idea |
| `validation` | `bootstrap_ci / monte_carlo / permutation / sensitivity / stability(result)` | Vibe idea (the quality differentiator) |
| `benchmark` | `compare(equity) -> {buyhold, qqq, ndx, prop_target, rf}` | Vibe idea |
| `reporting` | `report(result) -> report.md + run_card.json + charts/` | Vibe "run cards" idea |
| `factors` | plugin registry: `@factor def trend(df)->series` (small, modular, NOT 461) | Vibe idea, minimal |
| `nl` | `parse("test RSI+vol filter") -> ExperimentSpec` via **your llm_bridge** (Qwen/GLM/Ollama), human-confirmed | your **delegation bridge** |

## 3. Data flow
```
NL request ("test RSI + vol filter")
  -> nl.parse (local Qwen/GLM, human-confirms the spec)      [never auto-runs]
  -> dataquality.check on the input snapshot                 [gate: bad data -> stop]
  -> experiments.run (grid / walk-forward / CV / sweep)
  -> validation battery (bootstrap CI, MC, permutation, sensitivity, stability)
  -> benchmark.compare (vs QQQ / buy&hold / prop target / rf)
  -> reporting.report -> experiments/EXP-.../report.md + run_card.json + charts
  -> registry entry (status: Rejected | Shadow | Validated | Archived | Live Candidate)
  -> [HUMAN REVIEW] -> hand-carry a Live Candidate into production's Research-OS queue
```
Every run writes a `run_card.json` (spec hash, data snapshot hash, seed, git commit,
metrics) so **every result is reproducible** — re-running the card reproduces the numbers.

## 4. Validation pipeline (the quality upgrade)
Each candidate must clear, in order (fail-fast):
1. **Data quality** — no bad bars in the tested window.
2. **In/out-of-sample** walk-forward (your gauntlet discipline).
3. **Bootstrap CI** — is the edge's 95% CI above zero net of costs?
4. **Monte-Carlo / permutation** — beat shuffled-label / random-entry nulls?
5. **Sensitivity + parameter-stability** — edge survives ±param perturbation (no cliff).
6. **Benchmark** — beats QQQ buy-hold and clears the prop target on a risk-adjusted basis.
A result that fails any step is registered `Rejected` with the reason (the graveyard rule).

## 5. Promotion pipeline (nothing reaches production automatically)
```
Research -> Validation -> Walk-Forward -> Shadow -> HUMAN REVIEW -> Production
```
Research Lab OWNS: Research, Validation, Walk-Forward, and producing the Shadow SPEC.
It STOPS at "Live Candidate + human review." Production's EXISTING pipeline (forward
shadow, committee, clock-reset governance) owns everything from Shadow onward. The lab
never promotes; a human moves the candidate, and it then obeys production's clock/committee.

## 6. Feature ranking (Research Value / Impl Cost / Complexity / Expected Impact)
| # | Feature | Research Value | Impl Cost | Complexity | Expected Impact | Build order |
|---|---|---|---|---|---|---|
| 1 | Data-quality checks | HIGH | LOW | LOW | HIGH (protects every result) | **1st** |
| 2 | Idea registry | HIGH | LOW | LOW | HIGH (reproducible, tracked) | **2nd** |
| 3 | Experiment runner (grid/WF/CV) + research engine | HIGH | MED | MED | HIGH (the core capability) | **3rd** |
| 4 | Validation battery (bootstrap/MC/perm/sensitivity/stability) | HIGH | MED | MED-HIGH | HIGH (the quality differentiator) | **4th** |
| 5 | Benchmarking | MED | LOW | LOW | MED | 5th |
| 6 | Reporting / run cards | MED | LOW-MED | LOW | MED (reproducibility) | 6th |
| 7 | Modular factor engine | MED-HIGH | MED | MED | MED (enables discovery) | 7th |
| 8 | Promotion pipeline (process + manual hand-off) | HIGH | LOW | LOW | HIGH (keeps prod disciplined) | 8th (mostly docs) |
| 9 | Research dashboard (separate, :8502) | MED | MED | MED | MED | 9th |
| 10 | Natural-language research | MED | MED | MED-HIGH | MED (UX; misparse risk -> human-gated) | **last** |

**Recommended MVP (first approval slice):** #1 data-quality + #2 registry + #3 runner +
#4 validation. That is a working quant desk: pose an experiment spec, run it walk-forward,
get bootstrap/MC-validated metrics + a reproducible run card + a registry entry. Benchmark,
reporting, factors, dashboard, and NL layer on top later. NL is LAST (highest UX risk,
lowest core value) and always human-confirms before running.

## 7. What we deliberately do NOT build (per the brief)
React frontend · FastAPI backend · Docker stack · 13 LLM providers (reuse your local
Qwen/GLM/Ollama bridge) · any broker/execution/order code · a second risk engine · a
duplicate production dashboard · 461 hardcoded factors (small modular plugins instead) ·
swarm multi-agent orchestration.

## 8. Interfaces to existing assets (reuse, not rebuild)
- **LLM:** the research `nl` module SHELLS the same local models via the existing bridge
  pattern (Qwen 7B/14B, GLM) — no new providers, no API keys in research.
- **Governance:** the registry statuses and promotion mirror your Research-OS
  (ideas/experiments/graveyard/committee), so a promoted candidate lands in a pipeline
  you already run.
- **Data:** read-only price snapshots copied from production; a snapshot hash in every
  run card ties results to exact inputs.

## Approval gate
This is the Phase-1 architecture. **No code is written until you approve.** On approval,
I implement the MVP slice (#1–#4) as the new `research-lab/` repo — production untouched.
