# MT5 → Mac live-evidence bridge — operating guide

_Measurement automation. Strictly READ-ONLY toward MT5. Raw evidence lives ONLY in the
private `nas100-live-evidence` repo — never in the public `nas100-trader` repo._

## Flow
```
MT5 VPS → export_mt5_evidence.py (read-only) → private repo nas100-live-evidence
        → Mac pull_live_evidence.sh → reconcile_live_evidence.py → reports/ + Trading OS
        → (optional Qwen/GLM first-pass) → Claude final review
```

## One-time setup
1. **Create the private GitHub repo** `nas100-live-evidence` (PRIVATE). Clone it on both:
   - VPS: `git clone <url> C:\Users\Administrator\nas100-live-evidence`
   - Mac: `git clone <url> ~/nas100-live-evidence`  (or set `LIVE_EVIDENCE_DIR`)
2. **Phase-1 probe (VPS, once):** run `python scripts/ops/probe_vps_env.py` **as the
   scheduler account** and paste the JSON back. It reveals the exact repo path, the
   MT5-capable interpreter, the terminal path, and whether MT5 connects — do not guess
   these. (SYSTEM usually cannot see the live terminal; use the interactive account.)
3. **Install the scheduler (VPS, Admin PowerShell):**
   ```
   powershell -ExecutionPolicy Bypass -File scripts\ops\install_evidence_task.ps1 `
     -Repo "<repo>" -Evidence "<evidence repo>" -Python "<mt5 python.exe>" -RunUser "ALPHAZONE\Administrator"
   ```
   Registers `nas100-evidence-export` — INDEPENDENT of trading / nas100-update / watchdog.

## Daily (automatic)
- VPS task runs `sync_mt5_evidence.ps1` after the final session (and after overnight):
  export → verify manifest+checksums+secrets → push the new `daily/<date>/` to the
  private repo. Never force-pushes, never deletes history, GitHub-down keeps local.
- Mac: `./scripts/ops/pull_live_evidence.sh` then
  `python scripts/ops/reconcile_live_evidence.py --snapshot ~/nas100-live-evidence/daily/<date>`
  → `reports/<date>_LIVE_EVIDENCE.md` + `reports/latest.json` + `reports/latest` pointer.
- **Trading OS → Evidence menu:** Evidence Status · Pull Evidence · Open Latest · Run Reconciliation.

## Snapshot contents (`daily/YYYY-MM-DD/`)
`account.json` (masked), `positions.csv`, `orders.csv`, `deals.csv`, `fills.csv`,
`execution_events.csv`, `scheduler.json`, `git_state.json`, `data_quality.json`,
`manifest.json` (generated_at_utc, hostname, **masked account hash only**, source commit,
row counts, SHA-256 per file, exporter version, success). No login/password/server/token
ever leaves the VPS — `verify_manifest.py` refuses to commit any file matching a secret.

## Reconciliation statuses
`HEALTHY` · `INCOMPLETE_DATA` · `EXECUTION_ANOMALY` · `EXPORT_FAILED` · `INSUFFICIENT_SAMPLE`.
Below **n=10** fills → `INSUFFICIENT_SAMPLE`; no strategy-profitability claim is made.
Unknown live metrics stay **UNKNOWN** — never estimated.

## Optional multi-model first-pass (Phase 9)
When a snapshot has enough observations, delegate a bounded first-pass via the existing
bridge (never raw secrets, never full account id):
`python scripts/router/task_router.py delegate <task> --backend qwen`  (7B: row/schema
reconciliation · 14B: cross-file anomalies · GLM: statistics only at sufficient n).
Claude reviews all model output; models cannot execute commands or modify production.
**Do not delegate below the minimum sample.**

## What changed in the trading system: NOTHING
The exporter is read-only (allowlist guard raises on `order_send`/close/modify; test #20
asserts no mutating call exists in the file). The only production edit in this whole
effort was `signal_timestamp` telemetry (commit `ce77588`) — an argument-only passthrough,
proven behavior-neutral by test #19/#19b. Governance: **operational telemetry, NOT
signal-touching → no evidence-clock reset.**

## Rollback
```
git revert add232b   # exporter + reconciler + tests
git revert 62d9eaa   # VPS sync + scheduler + probe
git revert <this>    # mac pull + launcher evidence controls + docs
git revert ce77588   # signal_timestamp telemetry (if ever suspected)
```
Then: `python -m py_compile live_trader.py`, `python status.py`, dashboard HTTP 200.
Reverting any of these removes only measurement plumbing — trading is untouched either way.
