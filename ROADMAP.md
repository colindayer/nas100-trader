# ROADMAP

## FROZEN — do not change without evidence of a defect
- Entry and exit logic of BOT_A–BOT_H
- Risk policy: 0.05–0.10% experimental, 0.25% ceiling, 0.75% total, 0.15% per playbook group
- Stop geometry floors: 30× spread, 15% D1 ATR, 2× recent M1 excursion
- CIO ranking: structural fit dominant, posterior bounded ×0.5–1.5
- Bayesian shrinkage toward priors

## CURRENT MISSION — 30 valid trades
Not profit. The question is whether the desk can measure reality correctly.
Tracked in `DAILY_VALIDATION.md`; any instrumentation metric below 100% means
**infrastructure first, never a strategy change.**

## IN PROGRESS
- Phase 2 structured JSONL events with machine-readable reason codes
- Phase 3 `desk_orchestrator.py` — health + evidence coordination
- Phase 4 daily validation pipeline

## BLOCKED ON A HUMAN DECISION
- VPS→Mac transport (GitHub token) — see `HUMAN_ACTION_REQUIRED.md`
- LLM worker (Anthropic key) — recurring cost, optional, never a trading dependency

## EXPERIMENTAL
- Shadow variants v2–v8: recorded on every signal, promotion needs repeated outperformance
- State-conditional expectancy: returns `INSUFFICIENT_EVIDENCE` below 30 samples per class

## RETIRED
- **BOT_I** asia-sweep→London-reversal. 2y XAUUSD: 519 sessions → 15 trades = 7.3/year,
  t=+0.50, 0 reached TP2. Unfalsifiable inside any useful horizon. Class kept for its funnel.

## STANDING RULES EARNED THE HARD WAY
- Any candidate with >3 conditions gets a **frequency** backtest before deployment.
- Cost/R outranks entry rules: on a zero-edge system, 10%R→2%R moves P(pass) 9.2%→31.6%.
- Voiding is for instrumentation faults only. A loss is evidence.
- Never conclude from n=1.
