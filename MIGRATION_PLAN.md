# MIGRATION PLAN — V1 (running) → V2 (ARCHITECTURE_V2)

_Small, PR-sized, reversible phases. **V1 keeps trading demo throughout.** No big-bang
rewrite. Each phase names exact files + a verification check. Nothing here is executed
yet — this is the plan._

## Invariants (every phase must hold)
- The live path (`live_trader.py` + `broker.py` + `*_broker.py` + `alerts.py`) keeps
  working. **Paper/demo trading never stops.**
- No archived/moved file is imported by the live path (verified per phase).
- Each phase is independently revertible (`git revert`).

## Global pre-check (run before every phase)
```
python -c "import ast; ast.parse(open('live_trader.py').read())"   # parses
python status.py                                                   # venues green, tasks LastResult=0
```

---

### Phase 0 — Freeze & tag V1  (docs/git only)
- **Touches:** none (git tag).
- **Do:** `git tag v1-frozen && git push --tags`. V1 is now a named safe point.
- **Verify:** `git tag | grep v1-frozen`.

### Phase 1 — Vault consolidation  (docs only)
- **Touches:** `vault/`, `obsidian_vault/` (see [[VAULT_CONSOLIDATION_PLAN]]).
- **Do:** flatten `vault/vault/*` → `vault/`; `rmdir obsidian_vault`.
- **Verify:** `find vault -name "*.md" | wc -l` == 31; `test ! -d vault/vault`;
  open Dashboard in Obsidian, Dataview renders.
- **Risk:** none (documentation).

### Phase 2 — Archive the experiment sprawl  (no production import touched)
- **Touches:** move 62 `Experiment` + 14 `Obsolete` + 5 `Duplicate` files (per
  [[CODE_INVENTORY]]) into `research/archive/`. Delete the 5 `full_yearly.py.backup_*`
  and `sweep_backtest.py .py` **only after** confirming unused.
- **Do:** `mkdir -p research/archive && git mv <file> research/archive/` per file.
- **Verify (critical):**
  ```
  # no archived file is imported by the live path:
  for m in $(ls research/archive/*.py | xargs -n1 basename | sed 's/.py//'); do
    grep -REl "^(from|import) $m\b" live_trader.py broker.py *_broker.py alerts.py status.py && echo "STILL USED: $m";
  done
  python -c "import live_trader"      # still imports clean
  python status.py                    # still green
  ```
- **Risk:** low — these are orphan scripts. If any check flags "STILL USED", leave that file.

### Phase 3 — Group live code into `src/`  (structure only, behavior identical)
- **Touches:** `git mv` into `src/engine/` (live_trader.py), `src/brokers/`
  (`broker.py` + `*_broker.py`), `src/exec/` (alerts.py), `tools/` (status, watchdog,
  test_order, protect_positions, diag_live, verify_liveness, check_health, setup_telegram),
  `src/data/` (fetch_*, download_data). Add a thin root `live_trader.py` shim that
  imports from `src/engine` so the VPS `.bat` path is unchanged (or update `schedule_mt5.ps1`).
- **Do:** move + fix imports; keep a compatibility shim.
- **Verify:** `python -m src.engine.live_trader --broker mt5 --session all --dry-run`
  runs to "END session"; `python status.py` green; VPS scheduled `.bat` still resolves.
- **Risk:** medium (import paths). Ship behind the shim; revert is one commit.

### Phase 4 — Alpaca bracket orders  (small code PR)
- **Touches:** `alpaca_broker.py` only (`place_order` gains `sl/tp` → Alpaca bracket order).
- **Do:** implement bracket; `place_order_safe` already passes `sl/tp`.
- **Verify:** `python test_order.py` against Alpaca paper shows a bracket order in the
  Alpaca dashboard; existing MT5 path untouched.
- **Risk:** low (paper). Closes an [[LIVE_SAFETY_AUDIT]] item.

### Phase 5 — `sessions.yaml` single source for schedulers  (config only)
- **Touches:** new `sessions.yaml`; `schedule_mt5.ps1` + `.github/workflows/main.yml`
  generated from it (or documented as derived).
- **Do:** extract the current cron/session list verbatim into YAML.
- **Verify:** diff generated schedule vs current `schtasks /query` output — **identical**.
- **Risk:** low.

### Phase 6 — Strategy plugin contract  (structural, no logic change)
- **Touches:** wrap each `run_sX` in a `Strategy` class exposing `signal()` + a declared
  `exit_policy`/`stop_pct`. Loader **rejects** `bracket` strategies with no `stop_pct`.
- **Do:** mechanical wrap; strategy math byte-identical.
- **Verify:** `verify_liveness.py` signal counts unchanged; a deliberately stop-less
  test strategy fails to load; gauntlet CI added.
- **Risk:** medium — do one strategy at a time, compare live-vs-wrapped signal counts.

### Phase 7 — `MAX_OPEN_RISK` cap  (risk PR)
- **Touches:** `broker.py`/risk engine — refuse new entry if Σ open-stop-distance > cap.
- **Do:** add cap + unit test.
- **Verify:** unit test; live behavior unchanged when under cap.
- **Risk:** low.

---

## Sequencing rationale
Phases 0–2 are **pure cleanup** (no behavior change) and can ship immediately. Phases
3–7 are the real V2 build — each is small, verifiable, and leaves V1 trading demo the
whole time. **Do not start Phase 4+ until the live edge shows signs of confirming**
([[10 Roadmap]] in the vault) — engineering V2 on an unconfirmed edge is premature.

## What this plan explicitly avoids
- No new strategies, no performance tuning (out of scope).
- No simultaneous multi-module rewrite.
- No deletion without a passing "provably unused" check.

Related: [[CODE_INVENTORY]] · [[VAULT_CONSOLIDATION_PLAN]] · [[ARCHITECTURE_V2]]
