# R1 Implementation Report — BTCTREND emergency broker-side floor

Scope: eliminate the naked-position failure mode for BTCTREND (the one 🟡 MED item in
LIVE_SAFETY_AUDIT.md). Normal strategy behavior preserved. Nothing else in C3 implemented.

## Files changed

| File | Change |
|------|--------|
| `emergency_protection.py` **(new)** | `emergency_floor()` (fail-loud validation), `needed_sl()` (never-loosen rule), `ensure_btc_protection()` (repair path: detect naked/loose → attach/ratchet → verify retcode → alert on failure) |
| `live_trader.py` (`run_btc_trend` only, ~15 lines) | (a) buy orders now pass `sl=emergency_floor(price,"long")` — attached atomically with the entry via the existing `place_order_safe(sl=)`/MT5 `order_send` path; sells (reductions) unchanged; (b) `ensure_btc_protection()` runs **every** daily run, before the no-rebalance tolerance return, so a held position is repaired/ratcheted even on quiet days |
| `test_emergency_protection.py` **(new)** | 16 tests (below) |
| `docs/R1_IMPLEMENTATION_REPORT.md` **(new)** | this report |

No other strategy touched (locked by test `test_other_strategies_untouched`).

## Evidence for the stop policy

Research study (research-lab `experiments/r1_emergency_stop/`, BTC daily OHLC 2019-01→
2026-06 from the production hourly export; exact replication of the live Donchian 20/10 +
20% vol-target signal; stops evaluated against intraday LOWS, broker-style):

| Policy | CAGR | Sharpe | MaxDD | stop hits/yr | premature rate |
|--------|------|--------|-------|--------------|----------------|
| none (current live) | +22.2% | 1.28 | −27.4% | 0 | — |
| 3×ATR20 | +13.3% | 1.23 | −13.6% | 6.94 | 94% |
| 4×ATR20 | +13.9% | 1.13 | −18.5% | 5.87 | 73% |
| 5×ATR20 | +15.2% | 1.06 | −24.7% | 4.54 | 62% |
| 6×ATR20 | +20.9% | 1.28 | −24.1% | 3.60 | 52% |
| fixed 10% | +21.5% | 1.31 | −26.2% | 3.87 | 69% |
| fixed 15% | +20.6% | 1.19 | −28.1% | 1.87 | 50% |
| **fixed 20% (selected)** | **+22.2%** | **1.28** | **−27.4%** | **0.40** | 3 events in 7.5y |

- **ATR multiples rejected on evidence**: after calm periods ATR compresses, the floor sits
  near price and fires constantly — high premature rates, 1–9 CAGR points destroyed. Wrong
  tool for a catastrophe floor on BTC.
- **Fixed 20% selected**: statistically transparent (CAGR/Sharpe/MaxDD identical to no-stop
  to reported precision; challenge simulation pass-rate 0.282 vs 0.283, DD-violation
  probability unchanged), fires 0.4×/yr and only in genuine −20% crashes, caps the dead-bot
  giveback near −20% from the last daily ratchet (a stop is a market order on trigger —
  gap-through slippage can fill below the level; jump-stress research is the C3.5 answer)
  vs **−25.9% worst observed** unmanaged in-trend giveback (unbounded in a future crash). Requires no volatility input →
  immune to the NaN-ATR failure mode by construction.
- No take-profit added (no evidence for one; R1 mandate respected).

`EMERGENCY_STOP_PCT = 0.20` is a constant, documented as evidence-selected and not tunable
without re-running the study.

## Tests added (16, all passing)

- Floor math: long/short levels; NaN/inf/zero/negative price and bad pct **raise** (fail
  safe = fail loud); never-loosen rule (naked→protect, looser→tighten, tighter→keep, both sides).
- Repair path (fake MT5 terminal): naked long repaired + broker ack verified; naked short
  repaired; tighter existing stop never loosened (nothing sent to broker); **restart/re-run
  idempotent** (second run modifies nothing); broker rejection → counted failed + alert
  fired + still-naked state reported honestly; dry-run/paper broker → clean no-op.
- Entry path (drives the **real** `MT5Broker.place_order` against the fake terminal):
  SL present in the same `order_send` request as the entry (atomic); broker rejection →
  `RuntimeError`, **no naked position exists**.
- Behavior preservation (source-level locks): Donchian 20/10 signal lines byte-identical;
  vol-target constant unchanged; buys carry SL / sells don't; no `tp=` anywhere in
  `run_btc_trend`; repair runs before the tolerance return; `run_s1..s5`, `run_btc`,
  `run_overnight` reference nothing from the new module.

## Test results

- `test_emergency_protection`: **16/16 OK**
- `test_mt5_reconnect`: OK
- `test_fill_ledger`: FAILED — **pre-existing** (identical failure with R1 stashed;
  unrelated module-import issue)
- `live_trader.py` / `emergency_protection.py` compile clean
- research-lab suite: **122/122 OK** (evidence snapshot is data-only; no research code changed)
- Mac dry-run note: `--dry-run --session btctrend` can't exercise MT5 locally (module is
  VPS-only); the entry/repair paths are covered by the fake-terminal tests. **Next step for
  review: VPS dry-run** (`python live_trader.py --broker mt5 --dry-run --session btctrend`),
  then one live daily run and confirm the SL column populates in the MT5 terminal.

## Before / after

| Scenario | Before | After |
|----------|--------|-------|
| New BTCTREND entry | naked (state-machine exit only) | broker SL at −20% attached atomically; rejection ⇒ no position |
| Held position, bot/VPS/network dies | unbounded giveback (−25.9% observed worst) | broker enforces ~−20% floor from last daily ratchet (gap slippage possible) |
| Existing naked position at next daily run | stays naked | detected + repaired + verified; alert if repair fails |
| Existing tighter stop (e.g. sweep bracket) | — | never loosened |
| Normal Donchian trend exit | rebalance to flat | unchanged (identical signal path) |

## Rollback

`git revert <R1 commit>` — the change is one commit: two new files + the `run_btc_trend`
block. No state-file format changed; no other strategy references the module. Positions
already carrying the emergency SL keep it (harmless); remove manually in MT5 if desired.

## Confirmation

No other strategy's behavior changed (test-locked). Research firewall intact: the evidence
study ran in research-lab on a data copy; research code is unchanged.
