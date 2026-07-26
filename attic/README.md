# attic — components that failed the complexity rubric

Shelved, not deleted, for traceability. Each failed at least one of:
1. What measurable problem does it solve?
2. What evidence shows the existing architecture cannot solve it?
3. How will we measure whether it improved the platform?
4. Can we remove it if it fails?

| file | why shelved |
|--|--|
| `gsr_strategy.py` | zero importers; no runner could ever reach it |
| `tradingview_bridge.py` | never invoked by any code path; MT5 is authoritative for all decisions |
| `prop_objective.py` | never consulted at order time; prop survival is enforced by the Guardian |

**Not shelved but flagged:** `execution_safety/belief_reader.py` (v1) is still imported by
`portfolio_mt5.py --live` and `market_intel/web.py`. It requires migration to `belief_graph_v2`
before it can be retired — deleting it now would break the legacy path.
`market_intel/engine.py` is retained: it is the architectural opportunity path and is covered by
tests, though no scheduled runner invokes it yet.

Restoring is a `git mv` back. Nothing here is referenced by `MANIFEST.json`.
