# OPPORTUNITY_REGISTRY

An Opportunity is **evidence**, not an order.

## Fields
`opportunity_id · created_at · instrument · direction · confidence · expected_volatility ·
economic_reasoning · technical_confirmation · regime_compatibility · kill_zone_alignment ·
risk_estimate · stop_suggestion · target_suggestion · expected_holding_period ·
evidence_supporting · evidence_contradicting · source_event_id · status · pipeline_log`

`confidence` is **evidence weight, not probability of profit.**

## Lifecycle
`REGISTERED → EVALUATED → SHADOW_ALLOWED | REJECTED`

Generated only from a **released** event (`from_release` returns `None` if `actual` is missing).
Persisted append-only to `registry/opportunities.jsonl`.

## Governance
`evaluate_through_pipeline()` routes each opportunity through the PHASE 601 gate. If the Belief
Graph or Guardian is not supplied it returns `RESEARCH_ONLY` — **fail closed, never an implicit
allow**. Both supporting *and* contradicting evidence are recorded on every opportunity, so a
rejection is as auditable as an approval.
