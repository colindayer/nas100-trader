# HEALTHCHECK

One command verifies the whole installation.

```
py healthcheck.py            # full check, PASS/WARN/FAIL/SKIP per subsystem
py healthcheck.py --quick    # skip network + broker probes (fast, offline-safe)
py healthcheck.py --json     # machine-readable
```

Exit code **0** if no CRITICAL subsystem failed, else **1** — usable in a scheduled task.

## Subsystems checked
| subsystem | critical | what it proves |
|--|--|--|
| version | no | VERSION.json readable; warns if the working tree has moved past it |
| files | **yes** | every file in `VERSION.json:required_files` exists |
| modules | **yes** | all 15 core modules import cleanly |
| environment | no | which provider/alert variables are set on THIS machine |
| calendar_providers | no | implemented / configured / tested / active per provider |
| contracts | no | contracts load; which are demo- or live-eligible |
| belief_graph | **yes** | live Research + Operational belief, evidence count, exec cap |
| promotion | **yes** | live state, caps, blocking requirements; **fails if the LIVE bar ≠ 0.60** |
| execution_gate | **yes** | actively blocks an unknown strategy; guard blocks an unarmed submit |
| guardian | **yes** | bridge reachable; a BLOCK verdict is reported as correct fail-closed behaviour |
| ledger | **yes** | ledger loads; orphan policy responds |
| reconciliation | **yes** | a naked (stopless) position is flagged CRITICAL |
| demo_envelope | **yes** | position cap, daily cap and halt all enforced |
| broker | no | MT5 connectivity, DEMO/REAL, equity |
| telegram | no | configured? (and states plainly that no runner emits alerts yet) |
| entry_points | no | all four documented entry points exist on disk |

`*` in the output marks a critical subsystem. **A critical FAIL means the platform must not execute.**

## Provider reporting
Providers are reported on four independent axes and never inferred from source alone:

| axis | meaning |
|--|--|
| implemented | the adapter exists in code |
| configured | credentials/settings present **on this machine** |
| tested | a live probe succeeded **just now** (`-` when not probed, e.g. `--quick`) |
| active | the provider the runtime would actually use for the next call |
